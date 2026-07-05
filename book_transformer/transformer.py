"""Scrape Kindle Notebook highlights via Playwright.

Two modes share the exact same extraction code, so the emitted note dicts
are identical either way:

* ``xhr`` (default) — fetch each book's annotation fragment directly from the
  endpoint the notebook UI itself calls when a book is clicked
  (``/notebook?asin=...``), following the hidden pagination token so large
  books are complete. No clicks, no fixed waits.
* ``dom`` — the legacy click-driven walk, kept as an automatic fallback when
  the XHR shape changes, and forceable via ``SCRAPE_MODE=dom``. Its old blind
  1.5s pause is replaced by waiting for the clicked book's annotation
  response.

Each emitted note dict carries the v2 identifiers as well, so downstream
writers (``google_sheets/toSheets.py``) can stay deterministic without
having to re-derive them.
"""

import os
import re
from collections import defaultdict

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from note_utils import stable_book_id

NOTEBOOK_URL = "https://read.amazon.co.jp/notebook"
BOOK_SELECTOR = ".kp-notebook-library-each-book"
BOOK_TITLE_SELECTOR = "h3"
HIGHLIGHT_SELECTOR = "#highlight"
PAGE_INFO_SELECTOR = "#annotationHighlightHeader"
NEXT_PAGE_TOKEN_SELECTOR = ".kp-notebook-annotations-next-page-start"
CONTENT_LIMIT_STATE_SELECTOR = ".kp-notebook-content-limit-state"

SCRAPE_MODE_ENV = "SCRAPE_MODE"
LOAD_TIMEOUT = 60000
BOOK_SWITCH_WAIT_MS = 1500          # legacy fixed pause (DOM-mode safety net)
BOOK_SWITCH_SETTLE_MS = 200         # DOM swap settle after the XHR arrives
BOOK_SWITCH_RESPONSE_TIMEOUT_MS = 10000
MAX_ANNOTATION_PAGES = 100          # per book; guards a runaway pagination loop

# What the last extract_notes() call actually used: "xhr" | "dom" |
# "dom-fallback". Recorded into run history so a silent fallback is visible.
last_scrape_mode = None


class XhrScrapeError(RuntimeError):
    """XHR mode could not proceed; the caller falls back to DOM mode."""


def _get_book_elements(page):
    return page.query_selector_all(BOOK_SELECTOR)


def extract_notes(page, max_books=None, progress_callback=None):
    global last_scrape_mode

    mode = (os.getenv(SCRAPE_MODE_ENV) or "xhr").strip().lower()
    if mode != "dom":
        try:
            notes = _extract_notes_xhr(page, max_books, progress_callback)
            last_scrape_mode = "xhr"
            return notes
        except Exception as exc:
            print(
                f"XHR scrape failed ({type(exc).__name__}: {exc}); "
                "falling back to DOM mode."
            )
            last_scrape_mode = "dom-fallback"
            return _extract_notes_dom(page, max_books, progress_callback)

    last_scrape_mode = "dom"
    return _extract_notes_dom(page, max_books, progress_callback)


# ---------------------------------------------------------------------------
# Shared extraction (both modes emit notes through this single code path)
# ---------------------------------------------------------------------------


def _extract_current_book(page, book_title, book_id, per_book_index, notes):
    """Collect the highlights currently rendered on ``page``."""
    highlights = page.query_selector_all(HIGHLIGHT_SELECTOR)
    for highlight in highlights:
        content = (highlight.text_content() or "").strip()
        if not content:
            continue

        page_info_element = highlight.query_selector(PAGE_INFO_SELECTOR)
        location_value = ""
        if page_info_element:
            page_info_text = (page_info_element.text_content() or "").strip()
            match = re.search(r"\d+", page_info_text)
            if match:
                location_value = match.group(0)

        per_book_index[book_id] += 1
        notes.append(
            {
                "title": book_title,
                "content": content,
                "page": location_value,
                "location": location_value,
                "book_id": book_id,
                "idx_within_book": per_book_index[book_id],
            }
        )


# ---------------------------------------------------------------------------
# XHR mode
# ---------------------------------------------------------------------------


def _annotation_url(asin, token=None, limit_state=""):
    url = f"{NOTEBOOK_URL}?asin={asin}&contentLimitState={limit_state}&"
    if token:
        url += f"token={token}"
    return url


def _next_page_params(page):
    token_element = page.query_selector(NEXT_PAGE_TOKEN_SELECTOR)
    token = (token_element.get_attribute("value") or "").strip() if token_element else ""
    limit_element = page.query_selector(CONTENT_LIMIT_STATE_SELECTOR)
    limit_state = (limit_element.get_attribute("value") or "").strip() if limit_element else ""
    return token, limit_state


def _extract_notes_xhr(page, max_books, progress_callback):
    page.goto(NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.wait_for_selector(BOOK_SELECTOR, timeout=LOAD_TIMEOUT)

    asins = []
    for element in _get_book_elements(page):
        asin = (element.get_attribute("id") or "").strip()
        if not asin:
            raise XhrScrapeError("sidebar book without an ASIN id")
        asins.append(asin)
    if max_books is not None:
        asins = asins[:max_books]

    notes: list[dict] = []
    per_book_index: dict[str, int] = defaultdict(int)
    for index, asin in enumerate(asins):
        _fetch_book_via_xhr(
            page, asin, index, len(asins), per_book_index, notes, progress_callback
        )
    return notes


def _fetch_book_via_xhr(page, asin, index, total_books, per_book_index, notes,
                        progress_callback):
    """Fetch one book's annotation fragments (following pagination)."""
    token = None
    limit_state = ""
    book_title = None
    book_id = None

    for _page_number in range(MAX_ANNOTATION_PAGES):
        response = page.request.get(_annotation_url(asin, token, limit_state))
        if not response.ok:
            raise XhrScrapeError(f"HTTP {response.status} for asin {asin}")
        # Render the fragment on the live page so the extraction below uses
        # the exact same selectors as DOM mode (no separate HTML parser).
        page.set_content(response.text())

        if book_title is None:
            title_element = page.query_selector(BOOK_TITLE_SELECTOR)
            if title_element is None:
                raise XhrScrapeError(f"annotation fragment without a title for asin {asin}")
            book_title = (title_element.text_content() or "").strip()
            book_id = stable_book_id(book_title)
            if progress_callback:
                progress_callback(
                    "scrape",
                    index + 1,
                    total_books,
                    f"「{book_title}」のハイライトを取得中...",
                )

        _extract_current_book(page, book_title, book_id, per_book_index, notes)

        token, limit_state = _next_page_params(page)
        if not token:
            return

    raise XhrScrapeError(f"pagination did not terminate for asin {asin}")


# ---------------------------------------------------------------------------
# DOM mode (legacy walk, event-driven waits)
# ---------------------------------------------------------------------------


def _click_book_and_wait(page, book_element):
    """Click a sidebar book and wait for its annotations to load.

    Waits for the clicked ASIN's annotation response instead of the old
    blind 1.5s pause; the fixed pause remains as the safety net when no
    matching response arrives (e.g. re-clicking the selected book).
    """
    asin = (book_element.get_attribute("id") or "").strip()
    if not asin:
        book_element.click()
        page.wait_for_timeout(BOOK_SWITCH_WAIT_MS)
        return

    try:
        with page.expect_response(
            lambda response: f"asin={asin}" in response.url,
            timeout=BOOK_SWITCH_RESPONSE_TIMEOUT_MS,
        ):
            book_element.click()
        page.wait_for_timeout(BOOK_SWITCH_SETTLE_MS)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(BOOK_SWITCH_WAIT_MS)


def _extract_notes_dom(page, max_books, progress_callback):
    page.goto(NOTEBOOK_URL, timeout=LOAD_TIMEOUT)
    page.wait_for_selector(BOOK_SELECTOR, timeout=LOAD_TIMEOUT)

    books = _get_book_elements(page)
    total_books = len(books) if max_books is None else min(len(books), max_books)
    notes: list[dict] = []
    per_book_index: dict[str, int] = defaultdict(int)

    for index in range(total_books):
        books = _get_book_elements(page)
        _click_book_and_wait(page, books[index])
        page.wait_for_selector(BOOK_TITLE_SELECTOR, timeout=LOAD_TIMEOUT)

        book_title_element = page.query_selector(BOOK_TITLE_SELECTOR)
        if book_title_element:
            book_title = (book_title_element.text_content() or "").strip()
        else:
            book_title = f"Unknown Book {index + 1}"
            print(f"Warning: title not found for book {index + 1}.")

        book_id = stable_book_id(book_title)

        if progress_callback:
            progress_callback(
                "scrape",
                index + 1,
                total_books,
                f"「{book_title}」のハイライトを取得中...",
            )

        _extract_current_book(page, book_title, book_id, per_book_index, notes)

    return notes
