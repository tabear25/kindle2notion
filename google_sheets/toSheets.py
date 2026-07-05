"""Write Kindle highlights to Google Sheets in the v2 multi-sheet schema.

Two worksheets are managed by this module:

* ``01_books``      -- one row per book.
* ``02_highlights`` -- one row per highlight, FK ``book_id`` -> ``01_books``.

Other worksheets that may exist in the same spreadsheet (``03_book_summary``,
``04_highlight_tags``, ``05_tags_taxonomy``, ``00_README``, the legacy
``Sheet1``) are **never** read or modified here.

This module intentionally adds **no external AI/API dependency** beyond
``gspread`` + ``google-auth`` that the project already required.
"""

from __future__ import annotations

import json
from typing import Iterable

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from tqdm import tqdm

from note_utils import (
    BOOK_META_KEYS,
    BOOKS_HEADERS,
    HIGHLIGHTS_HEADERS,
    content_dedup_key,
    highlight_id,
    note_to_book_row,
    note_to_highlight_row,
    stable_book_id,
    today_iso,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BOOKS_SHEET = "01_books"
HIGHLIGHTS_SHEET = "02_highlights"

_BOOKS_DEFAULT_ROWS = 200
_HIGHLIGHTS_DEFAULT_ROWS = 5000

# (connect, read) timeout in seconds applied to every Sheets/Drive request.
# Without an explicit timeout, a stalled network call to Google's API blocks the
# worker thread forever, which the GUI / web UI surfaces as a "frozen" save.
# With it, a stall fails fast with an error instead of hanging indefinitely.
REQUEST_TIMEOUT = (10, 60)


def _build_client(service_account_file):
    service_account_source = (service_account_file or "").strip()
    if not service_account_source:
        raise ValueError("Google service account credential is empty.")

    if service_account_source.startswith("{"):
        credentials_info = json.loads(service_account_source)
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=SCOPES,
        )
    else:
        credentials = Credentials.from_service_account_file(
            service_account_source,
            scopes=SCOPES,
        )
    client = gspread.authorize(credentials)
    client.set_timeout(REQUEST_TIMEOUT)
    return client


def _open_spreadsheet(client, spreadsheet_id):
    """Open the spreadsheet by key, turning a missing / inaccessible sheet into a
    clear, actionable error.

    A wrong, deleted, or un-shared ``GOOGLE_SHEETS_SPREADSHEET_ID`` otherwise
    surfaces as a bare ``SpreadsheetNotFound`` / 404 with no hint about the fix.
    """
    try:
        return client.open_by_key(spreadsheet_id)
    except SpreadsheetNotFound as exc:
        raise RuntimeError(
            "Google スプレッドシートを開けませんでした"
            f"（GOOGLE_SHEETS_SPREADSHEET_ID={spreadsheet_id!r}）。"
            "IDが間違っている、スプレッドシートが削除済み、または対象がサービスアカウントに"
            "共有されていない可能性があります。config/KEYS.env のIDと、スプレッドシートの"
            "共有設定（サービスアカウントを編集者として共有）を確認してください。"
        ) from exc
    except APIError as exc:
        raise RuntimeError(
            "Google スプレッドシートへのアクセスに失敗しました"
            f"（GOOGLE_SHEETS_SPREADSHEET_ID={spreadsheet_id!r}）: {exc}"
        ) from exc


def _get_or_create_worksheet(spreadsheet, name: str, headers: list, default_rows: int):
    """Return the worksheet, creating it (with header row) if missing."""
    try:
        worksheet = spreadsheet.worksheet(name)
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.update("A1", [headers], value_input_option="RAW")
        return worksheet
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=name, rows=default_rows, cols=max(len(headers), 10)
        )
        worksheet.update("A1", [headers], value_input_option="RAW")
        return worksheet


def _row_to_dict(row, headers):
    padded = (list(row) + [""] * len(headers))[: len(headers)]
    return dict(zip(headers, padded))


def _load_books(worksheet) -> dict:
    """Return ``{book_id: row_dict}`` for every existing book row."""
    rows = worksheet.get_all_values()
    if not rows:
        return {}
    start = 1 if rows[0][: len(BOOKS_HEADERS)] == BOOKS_HEADERS else 0
    out: dict = {}
    for row in rows[start:]:
        if not any(c.strip() for c in row):
            continue
        d = _row_to_dict(row, BOOKS_HEADERS)
        bid = d.get("book_id", "").strip()
        if bid:
            out[bid] = d
    return out


def list_existing_books(service_account_file, spreadsheet_id) -> list[dict]:
    """Return existing books from ``01_books`` as lightweight dicts.

    Read-only: opens the spreadsheet and reads ``01_books`` without creating or
    modifying anything. Each entry is ``{"book_id", "title", "author",
    "highlight_count"}``. Used by the manual-entry tooling so an assistant can
    fuzzy-match a user-typed title against titles already on record and catch
    typos before they create a duplicate book (book_id is title-derived).
    Returns ``[]`` if the sheet is missing or empty.
    """
    client = _build_client(service_account_file)
    spreadsheet = _open_spreadsheet(client, spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(BOOKS_SHEET)
    except WorksheetNotFound:
        return []
    books = _load_books(worksheet)
    out = []
    for bid, row in books.items():
        title = (row.get("title") or "").strip()
        if not title:
            continue
        out.append(
            {
                "book_id": bid,
                "title": title,
                "author": (row.get("author") or "").strip(),
                "highlight_count": (row.get("highlight_count") or "").strip(),
            }
        )
    out.sort(key=lambda b: b["title"])
    return out


def _load_highlight_state(worksheet):
    """Return (dedup_set, max_idx_per_book) from ``02_highlights``."""
    rows = worksheet.get_all_values()
    if not rows:
        return set(), {}
    start = 1 if rows[0][: len(HIGHLIGHTS_HEADERS)] == HIGHLIGHTS_HEADERS else 0

    dedup = set()
    max_idx = {}

    for row in rows[start:]:
        if not any(c.strip() for c in row):
            continue
        d = _row_to_dict(row, HIGHLIGHTS_HEADERS)
        bid = d.get("book_id", "").strip()
        content = d.get("content", "").strip()
        hid = d.get("highlight_id", "").strip()
        if not bid or not content:
            continue

        dedup.add(content_dedup_key(bid, content))

        if hid.startswith("HL-") and "-" in hid[3:]:
            tail = hid.rsplit("-", 1)[-1]
            if tail.isdigit():
                idx = int(tail)
                if idx > max_idx.get(bid, 0):
                    max_idx[bid] = idx

    return dedup, max_idx


def _book_extra_from_note(note: dict) -> dict:
    """Pull human-supplied book metadata off a note dict.

    Kindle-scraped notes carry none of these keys, so this returns ``{}`` and
    ``note_to_book_row`` behaves exactly as before. Manually added books (see
    ``scripts/add_manual_highlights.py``) may carry ``author`` / ``genre`` /
    ``reading_status`` etc., which then populate the new book's row on
    ``01_books``.
    """
    return {key: note[key] for key in BOOK_META_KEYS if note.get(key)}


def save_notes_to_google_sheets(
    service_account_file,
    spreadsheet_id,
    notes: Iterable,
    progress_callback=None,
):
    """Append new books / highlights to the v2 schema worksheets.

    Returns a summary dict ``{"new_books", "new_highlights",
    "skipped_duplicates", "skipped_invalid", "total_notes"}``. Existing callers
    (GUI / web pipeline) ignore the return value; manual-entry tooling uses it
    to report what was written.
    """
    notes = list(notes)
    client = _build_client(service_account_file)
    spreadsheet = _open_spreadsheet(client, spreadsheet_id)

    books_ws = _get_or_create_worksheet(
        spreadsheet, BOOKS_SHEET, BOOKS_HEADERS, _BOOKS_DEFAULT_ROWS
    )
    highlights_ws = _get_or_create_worksheet(
        spreadsheet, HIGHLIGHTS_SHEET, HIGHLIGHTS_HEADERS, _HIGHLIGHTS_DEFAULT_ROWS
    )

    existing_books = _load_books(books_ws)
    existing_dedup, max_idx = _load_highlight_state(highlights_ws)

    today = today_iso()
    new_book_rows = []
    new_highlight_rows = []
    touched_books = {}
    skipped_invalid = 0
    skipped_duplicates = 0

    total = len(notes)
    for i, note in enumerate(tqdm(notes, desc="Sheets")):
        if progress_callback:
            progress_callback("sheets", i + 1, total, note.get("title", ""))

        title = (note.get("title") or "").strip()
        content = (note.get("content") or "").strip()
        if not title or not content:
            skipped_invalid += 1
            continue

        bid = note.get("book_id") or stable_book_id(title)

        if bid not in existing_books:
            new_book_rows.append(
                note_to_book_row(bid, title, today, extra=_book_extra_from_note(note))
            )
            existing_books[bid] = {"first_synced_at": today, "highlight_count": "0"}
        touched_books.setdefault(bid, 0)

        key = content_dedup_key(bid, content)
        if key in existing_dedup:
            skipped_duplicates += 1
            continue

        max_idx[bid] = max_idx.get(bid, 0) + 1
        supplied_idx = note.get("idx_within_book")
        if isinstance(supplied_idx, int) and supplied_idx > max_idx[bid]:
            max_idx[bid] = supplied_idx

        hid = highlight_id(bid, max_idx[bid])
        new_highlight_rows.append(note_to_highlight_row(hid, bid, note, today))
        existing_dedup.add(key)
        touched_books[bid] += 1

    if new_book_rows:
        try:
            books_ws.append_rows(new_book_rows, value_input_option="RAW")
        except Exception as e:
            print(f"Failed to append {len(new_book_rows)} rows to {BOOKS_SHEET}: {e}")

    if new_highlight_rows:
        try:
            highlights_ws.append_rows(new_highlight_rows, value_input_option="RAW")
        except Exception as e:
            print(
                f"Failed to append {len(new_highlight_rows)} rows to {HIGHLIGHTS_SHEET}: {e}"
            )

    if touched_books:
        try:
            _refresh_book_meta(books_ws, touched_books, today)
        except Exception as e:
            print(f"Failed to refresh book metadata on {BOOKS_SHEET}: {e}")

    return {
        "new_books": len(new_book_rows),
        "new_highlights": len(new_highlight_rows),
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
        "total_notes": len(notes),
    }


def _refresh_book_meta(books_ws, touched_books: dict, today: str) -> None:
    """Update highlight_count + last_synced_at columns for touched books."""
    rows = books_ws.get_all_values()
    if not rows:
        return
    start = 1 if rows[0][: len(BOOKS_HEADERS)] == BOOKS_HEADERS else 0

    count_col = BOOKS_HEADERS.index("highlight_count") + 1
    sync_col = BOOKS_HEADERS.index("last_synced_at") + 1

    updates = []
    for r_offset, row in enumerate(rows[start:], start=start + 1):
        d = _row_to_dict(row, BOOKS_HEADERS)
        bid = d.get("book_id", "").strip()
        if not bid or bid not in touched_books:
            continue
        try:
            current = int(d.get("highlight_count") or 0)
        except ValueError:
            current = 0
        new_count = current + touched_books[bid]
        col_letter_count = gspread.utils.rowcol_to_a1(r_offset, count_col)
        col_letter_sync = gspread.utils.rowcol_to_a1(r_offset, sync_col)
        updates.append({"range": col_letter_count, "values": [[new_count]]})
        updates.append({"range": col_letter_sync, "values": [[today]]})

    if updates:
        books_ws.batch_update(updates, value_input_option="RAW")
