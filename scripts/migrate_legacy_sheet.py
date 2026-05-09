"""One-shot migration: legacy ``Sheet1`` -> v2 ``01_books`` / ``02_highlights``.

Usage::

    python -m scripts.migrate_legacy_sheet                 # dry-run
    python -m scripts.migrate_legacy_sheet --apply         # actually write
    python -m scripts.migrate_legacy_sheet --apply --legacy-sheet "old"

The legacy worksheet is opened **read-only**; nothing is written back to it.
The destination worksheets are created if absent. If they already contain
data the script aborts to avoid clobbering work in progress.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# Make the project root importable when run as ``python scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402  (needs path-insertion above)
from google_sheets.toSheets import (  # noqa: E402
    BOOKS_SHEET,
    HIGHLIGHTS_SHEET,
    _build_client,
    _get_or_create_worksheet,
)
from note_utils import (  # noqa: E402
    BOOKS_HEADERS,
    HIGHLIGHTS_HEADERS,
    highlight_id,
    note_to_book_row,
    note_to_highlight_row,
    stable_book_id,
    today_iso,
)


DEFAULT_LEGACY_SHEET = "Sheet1"

# Column candidates in the legacy sheet (cope with manual additions).
TITLE_HEADERS = {"title", "Title"}
CONTENT_HEADERS = {"content", "Content"}
LOCATION_HEADERS = {"id", "ID", "location", "Location", "page", "Page"}


def _read_legacy_rows(spreadsheet, sheet_name: str) -> list[dict]:
    """Return list of {title, content, location} dicts from the legacy sheet."""
    ws = spreadsheet.worksheet(sheet_name)
    raw = ws.get_all_values()
    if not raw:
        return []

    header = raw[0]
    body = raw[1:]

    def find_col(candidates):
        for i, h in enumerate(header):
            if h in candidates:
                return i
        return None

    t_col = find_col(TITLE_HEADERS)
    c_col = find_col(CONTENT_HEADERS)
    l_col = find_col(LOCATION_HEADERS)

    if t_col is None or c_col is None:
        raise SystemExit(
            f"Legacy sheet '{sheet_name}' is missing required headers. "
            f"Saw: {header!r}"
        )

    out: list[dict] = []
    for row in body:
        title = (row[t_col] if t_col < len(row) else "").strip()
        content = (row[c_col] if c_col < len(row) else "").strip()
        location = (row[l_col] if l_col is not None and l_col < len(row) else "").strip()
        if not title or not content:
            continue
        out.append({"title": title, "content": content, "location": location})
    return out


def _build_v2_rows(legacy_notes: list[dict]):
    """Group legacy notes into books and highlights."""
    today = today_iso()
    book_rows: dict[str, list[str]] = {}
    book_order: list[str] = []
    highlight_rows: list[list[str]] = []
    counter: dict[str, int] = defaultdict(int)

    for note in legacy_notes:
        title = note["title"]
        bid = stable_book_id(title)
        if bid not in book_rows:
            book_rows[bid] = note_to_book_row(bid, title, today)
            book_order.append(bid)

        counter[bid] += 1
        hid = highlight_id(bid, counter[bid])
        # Pass location through note_to_highlight_row by populating both keys
        # so the normaliser picks the right one.
        adapted = {
            "title": title,
            "content": note["content"],
            "location": note["location"],
            "page": "",
            "highlighted_at": "",
        }
        highlight_rows.append(note_to_highlight_row(hid, bid, adapted, today))

    # Backfill highlight_count on each book row.
    count_col = BOOKS_HEADERS.index("highlight_count")
    for bid in book_order:
        book_rows[bid][count_col] = counter[bid]

    return [book_rows[b] for b in book_order], highlight_rows


def main_cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually write rows (default: dry-run)")
    parser.add_argument(
        "--legacy-sheet",
        default=DEFAULT_LEGACY_SHEET,
        help=f"name of the legacy worksheet (default: {DEFAULT_LEGACY_SHEET!r})",
    )
    args = parser.parse_args()

    main.load_config()
    if not main.GOOGLE_SHEETS_ENABLED:
        raise SystemExit(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE and "
            "GOOGLE_SHEETS_SPREADSHEET_ID in config/KEYS.env first."
        )

    client = _build_client(main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
    spreadsheet = client.open_by_key(main.GOOGLE_SHEETS_SPREADSHEET_ID)

    legacy_notes = _read_legacy_rows(spreadsheet, args.legacy_sheet)
    print(f"[legacy] {len(legacy_notes)} non-empty rows in '{args.legacy_sheet}'")

    book_rows, highlight_rows = _build_v2_rows(legacy_notes)
    print(f"[v2]     {len(book_rows)} books, {len(highlight_rows)} highlights")

    if not args.apply:
        print("\n(dry-run) re-run with --apply to write to Sheets.")
        return 0

    # Refuse to overwrite existing v2 data.
    for name in (BOOKS_SHEET, HIGHLIGHTS_SHEET):
        try:
            existing = spreadsheet.worksheet(name).get_all_values()
        except Exception:
            existing = []
        # Header-only is fine; anything more is not.
        if existing and any(any(c.strip() for c in row) for row in existing[1:]):
            raise SystemExit(
                f"Refusing to write: '{name}' already contains data. "
                f"Aborting to avoid clobbering."
            )

    books_ws = _get_or_create_worksheet(spreadsheet, BOOKS_SHEET, BOOKS_HEADERS, max(len(book_rows) + 50, 200))
    highlights_ws = _get_or_create_worksheet(
        spreadsheet, HIGHLIGHTS_SHEET, HIGHLIGHTS_HEADERS, max(len(highlight_rows) + 200, 1000)
    )

    if book_rows:
        books_ws.append_rows(book_rows, value_input_option="RAW")
    if highlight_rows:
        highlights_ws.append_rows(highlight_rows, value_input_option="RAW")

    print(f"\nWrote {len(book_rows)} rows to {BOOKS_SHEET}")
    print(f"Wrote {len(highlight_rows)} rows to {HIGHLIGHTS_SHEET}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
