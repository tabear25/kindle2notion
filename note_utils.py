"""Note utilities for kindle2notion.

This module provides:

1. Legacy helpers (``build_note_key`` / ``build_note_key_from_note`` /
   ``has_any_note_value`` / ``normalize_text``) kept intact so that
   ``notion/toNotion.py`` continues to work without modification.

2. New v2 helpers for the multi-sheet Google Sheets schema:

   - ``stable_book_id(title)`` returns ``"BK-<6hex>"`` -- deterministic across
     re-runs, so the same book title always maps to the same id.
   - ``highlight_id(book_id, idx_within_book)`` returns
     ``"HL-<book6>-<NNNN>"``.
   - ``content_dedup_key(book_id, content)`` returns a stable sha1 string
     used as the deduplication key on ``02_highlights``.
   - ``note_to_book_row`` / ``note_to_highlight_row`` shape a note dict into
     the row layout expected by each worksheet.

The new helpers do **not** depend on any external API; they are pure
functions so they can be unit-tested without network access.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Legacy helpers (kept for notion/toNotion.py)
# ---------------------------------------------------------------------------


def normalize_text(value: Any) -> str:
    """Coerce ``value`` to ``str`` and strip surrounding whitespace."""
    return str(value or "").strip()


def build_note_key(title, content, page) -> tuple[str, str, str]:
    """Legacy dedup key used by notion/toNotion.py."""
    return (
        normalize_text(title),
        normalize_text(content),
        normalize_text(page),
    )


def build_note_key_from_note(note: dict) -> tuple[str, str, str]:
    """Legacy variant that pulls fields from a note dict.

    The position falls back to ``location`` when ``page`` is empty. This value
    is both the Notion dedup key and what gets written to Notion's ``Page``
    property, so the two stay consistent across runs. Kindle-scraped notes carry
    only ``page`` (no ``location``), so their key is unchanged; manually added
    non-Kindle highlights -- which may supply a Kindle-style ``location`` instead
    of a page -- then keep that position in Notion too, instead of a blank
    ``Page``.
    """
    return build_note_key(
        note.get("title", ""),
        note.get("content", ""),
        note.get("page") or note.get("location", ""),
    )


def has_any_note_value(values: Iterable[str]) -> bool:
    return any(normalize_text(value) for value in values)


def note_key_hash(key: tuple[str, str, str]) -> str:
    """SHA1 hex digest of a Notion dedup key tuple.

    This is what the operational store caches instead of the raw
    ``(title, content, page)`` tuple, so highlight text never leaves
    Notion/Sheets. Fields are joined with a unit separator so shifted
    boundaries (``("a", "b|c")`` vs ``("a|b", "c")``) cannot collide.
    """
    joined = "\x1f".join(key)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# v2 helpers (new multi-sheet schema)
# ---------------------------------------------------------------------------

BOOK_ID_PREFIX = "BK-"
HIGHLIGHT_ID_PREFIX = "HL-"
BOOK_ID_HEX_LEN = 6


def _normalize_title(title: str) -> str:
    """Strip parenthetical publisher tags / extra whitespace.

    Used only for the human-readable ``title_normalized`` column on
    ``01_books``; the stable id is derived from the *raw* title (so that
    cosmetic edits never break dedup).
    """
    cleaned = re.sub(r"\s*[（(][^（(）)]*[)）]\s*", " ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def stable_book_id(title: str) -> str:
    """Deterministic ``BK-<6hex>`` from the raw book title.

    Same input -> same id, across machines and re-runs.
    """
    title_str = normalize_text(title)
    digest = hashlib.sha1(title_str.encode("utf-8")).hexdigest()
    return f"{BOOK_ID_PREFIX}{digest[:BOOK_ID_HEX_LEN].upper()}"


def highlight_id(book_id: str, idx_within_book: int) -> str:
    """Compose ``HL-<book6>-<NNNN>``.

    ``idx_within_book`` is 1-based and zero-padded to 4 digits.
    """
    if not book_id.startswith(BOOK_ID_PREFIX):
        raise ValueError(f"book_id must start with {BOOK_ID_PREFIX!r}: {book_id!r}")
    if idx_within_book < 1:
        raise ValueError(f"idx_within_book must be >= 1, got {idx_within_book}")
    book6 = book_id[len(BOOK_ID_PREFIX):]
    return f"{HIGHLIGHT_ID_PREFIX}{book6}-{idx_within_book:04d}"


def content_dedup_key(book_id: str, content: str) -> tuple[str, str]:
    """Return ``(book_id, sha1(content))`` -- the v2 dedup key."""
    content_hash = hashlib.sha1(normalize_text(content).encode("utf-8")).hexdigest()
    return (book_id, content_hash)


def today_iso() -> str:
    return datetime.date.today().isoformat()


BOOKS_HEADERS: list[str] = [
    "book_id",
    "title",
    "title_normalized",
    "author",
    "genre",
    "reading_status",
    "finished_at",
    "rating",
    "amazon_asin",
    "cover_url",
    "notion_url",
    "highlight_count",
    "first_synced_at",
    "last_synced_at",
]

HIGHLIGHTS_HEADERS: list[str] = [
    "highlight_id",
    "book_id",
    "book_title",
    "content",
    "location",
    "page",
    "highlighted_at",
    "synced_at",
    "source",
]

SOURCE_LABEL = "kindle2notion"

# Book metadata columns that a caller may pre-fill via the ``extra`` argument
# of ``note_to_book_row`` (e.g. when adding a physical / non-Kindle book by
# hand). The remaining columns (book_id, title, dates, highlight_count) are
# always managed by this module and never taken from ``extra``.
BOOK_META_KEYS: tuple[str, ...] = (
    "author",
    "genre",
    "reading_status",
    "finished_at",
    "rating",
    "amazon_asin",
    "cover_url",
    "notion_url",
)


def note_to_book_row(
    book_id: str,
    title: str,
    today: str | None = None,
    extra: dict | None = None,
) -> list[str]:
    """Initial row for a brand-new book on ``01_books``.

    ``extra`` lets a caller pre-fill the human-supplied metadata columns
    (see :data:`BOOK_META_KEYS`) when the book is added manually rather than
    scraped from Kindle. Only non-empty values override the defaults; unknown
    keys are ignored. Kindle scraping passes no ``extra`` and is unchanged.
    """
    today = today or today_iso()
    title = normalize_text(title)
    row = {
        "book_id": book_id,
        "title": title,
        "title_normalized": _normalize_title(title),
        "author": "",
        "genre": "",
        "reading_status": "",
        "finished_at": "",
        "rating": "",
        "amazon_asin": "",
        "cover_url": "",
        "notion_url": "",
        "highlight_count": "",
        "first_synced_at": today,
        "last_synced_at": today,
    }
    if extra:
        for key in BOOK_META_KEYS:
            value = normalize_text(extra.get(key, ""))
            if value:
                row[key] = value
    return [row[h] for h in BOOKS_HEADERS]


def note_to_highlight_row(hid: str, book_id: str, note: dict, today: str | None = None) -> list[str]:
    """Row for ``02_highlights``."""
    today = today or today_iso()
    row = {
        "highlight_id": hid,
        "book_id": book_id,
        "book_title": normalize_text(note.get("title", "")),
        "content": normalize_text(note.get("content", "")),
        "location": normalize_text(note.get("location") or note.get("page", "")),
        "page": normalize_text(note.get("page", "")) if note.get("location") else "",
        "highlighted_at": normalize_text(note.get("highlighted_at", "")),
        "synced_at": today,
        "source": normalize_text(note.get("source")) or SOURCE_LABEL,
    }
    return [row[h] for h in HIGHLIGHTS_HEADERS]
