"""Split master ``reading_note`` into per-book Sheets files for NotebookLM.

NotebookLM only ingests the **first** worksheet of each spreadsheet.
This script reads the v2 master schema (``01_books`` + ``02_highlights``),
groups highlights by book, and writes / refreshes one Google Sheets file
per book inside a ``per_book/`` subfolder next to the master spreadsheet.

Usage::

    python -m scripts.split_per_book                   # dry-run
    python -m scripts.split_per_book --apply           # actually write
    python -m scripts.split_per_book --apply --folder per_book

Design notes:

- Uses the same Service Account credential as the rest of the pipeline.
- No new external API / AI dependency.  Drive API calls go through
  ``google.auth.transport.requests.AuthorizedSession`` which is already a
  transitive dep of ``google-auth``.
- Idempotent: each per-book file is rewritten in full from the master.
  The master itself is **never** modified.
- Filename rule: ``<book_id>__<sanitised title>`` (Google-native sheets
  have no file extension).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Make the project root importable when run as ``python scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Heavy runtime imports are guarded so that unit tests can import the pure
# helpers without needing gspread / google-auth / nest_asyncio installed.
try:
    import gspread  # type: ignore
    from google.auth.transport.requests import AuthorizedSession  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
    from google_sheets.toSheets import BOOKS_SHEET, HIGHLIGHTS_SHEET, SCOPES  # noqa: E402
    from note_utils import BOOKS_HEADERS, HIGHLIGHTS_HEADERS  # noqa: E402
    _RUNTIME_DEPS_OK = True
except Exception:  # pragma: no cover -- only hit during test collection
    _RUNTIME_DEPS_OK = False

DRIVE_API = "https://www.googleapis.com/drive/v3"
DEFAULT_SUBFOLDER_NAME = "per_book"

# Columns on the per-book sheet (kept minimal so NotebookLM ingestion is clean).
PER_BOOK_HEADERS = ["highlight_id", "location", "content"]

# Maximum length for the title portion of the filename (book_id stays full).
TITLE_MAX_LEN = 80


# ---------------------------------------------------------------------------
# Pure helpers (covered by tests)
# ---------------------------------------------------------------------------


def safe_title_for_filename(title: str, max_len: int = TITLE_MAX_LEN) -> str:
    """Strip filesystem-unfriendly chars and collapse whitespace."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len].rstrip()


def per_book_filename(book_id: str, title: str) -> str:
    """``BK-XXXXXX__<safe_title>``.

    The filename does not include an extension; Google Sheets is a native
    Drive type so no extension is needed.
    """
    return f"{book_id}__{safe_title_for_filename(title)}"


def group_highlights_by_book(highlight_rows: list[dict]) -> dict[str, list[dict]]:
    """Group highlight dicts by book_id, preserving original ordering."""
    out: dict[str, list[dict]] = {}
    for row in highlight_rows:
        bid = (row.get("book_id") or "").strip()
        if not bid:
            continue
        out.setdefault(bid, []).append(row)
    return out


def per_book_rows(highlights_for_book: list[dict]) -> list[list[str]]:
    """Header + body for the per-book worksheet."""
    body = [
        [
            (h.get("highlight_id") or "").strip(),
            (h.get("location") or h.get("page") or "").strip(),
            (h.get("content") or "").strip(),
        ]
        for h in highlights_for_book
    ]
    return [PER_BOOK_HEADERS, *body]


# ---------------------------------------------------------------------------
# Sheets / Drive client
# ---------------------------------------------------------------------------


def _build_creds(service_account_file: str) -> Credentials:
    src = (service_account_file or "").strip()
    if not src:
        raise ValueError("Google service account credential is empty.")
    if src.startswith("{"):
        return Credentials.from_service_account_info(json.loads(src), scopes=SCOPES)
    return Credentials.from_service_account_file(src, scopes=SCOPES)


def _drive_session(creds: Credentials) -> AuthorizedSession:
    return AuthorizedSession(creds)


def _get_parent_folder(drive: AuthorizedSession, file_id: str) -> str:
    r = drive.get(f"{DRIVE_API}/files/{file_id}", params={"fields": "parents"})
    r.raise_for_status()
    parents = r.json().get("parents") or []
    if not parents:
        raise SystemExit(
            f"Master spreadsheet {file_id} appears to live in 'My Drive' root. "
            "Move it into a folder before running this script."
        )
    return parents[0]


def _find_or_create_subfolder(
    drive: AuthorizedSession, parent_id: str, name: str, *, dry_run: bool
) -> str | None:
    q = (
        f"\"{parent_id}\" in parents and "
        f"name = \"{name}\" and "
        "mimeType = \"application/vnd.google-apps.folder\" and trashed = false"
    )
    r = drive.get(
        f"{DRIVE_API}/files",
        params={"q": q, "fields": "files(id,name)", "pageSize": 10},
    )
    r.raise_for_status()
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]
    if dry_run:
        return None
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    r = drive.post(f"{DRIVE_API}/files", json=body)
    r.raise_for_status()
    return r.json()["id"]


def _list_spreadsheets_in_folder(
    drive: AuthorizedSession, folder_id: str
) -> dict[str, str]:
    """Return ``{filename: file_id}`` for every Sheets in ``folder_id``."""
    out: dict[str, str] = {}
    page_token = None
    while True:
        params = {
            "q": (
                f"\"{folder_id}\" in parents and "
                "mimeType = \"application/vnd.google-apps.spreadsheet\" and "
                "trashed = false"
            ),
            "fields": "nextPageToken, files(id,name)",
            "pageSize": 200,
        }
        if page_token:
            params["pageToken"] = page_token
        r = drive.get(f"{DRIVE_API}/files", params=params)
        r.raise_for_status()
        data = r.json()
        for f in data.get("files", []):
            out[f["name"]] = f["id"]
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def _create_spreadsheet_in_folder(
    drive: AuthorizedSession, parent_id: str, name: str
) -> str:
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [parent_id],
    }
    r = drive.post(f"{DRIVE_API}/files", json=body)
    r.raise_for_status()
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Master loaders
# ---------------------------------------------------------------------------


def _row_to_dict(row: list[str], headers: list[str]) -> dict:
    padded = (list(row) + [""] * len(headers))[: len(headers)]
    return dict(zip(headers, padded))


def _load_master(gc, spreadsheet_id: str) -> tuple[list[dict], list[dict]]:
    sh = gc.open_by_key(spreadsheet_id)

    books_ws = sh.worksheet(BOOKS_SHEET)
    raw_books = books_ws.get_all_values()
    if not raw_books:
        raise SystemExit(f"Master {BOOKS_SHEET} is empty.")
    start = 1 if raw_books[0][: len(BOOKS_HEADERS)] == BOOKS_HEADERS else 0
    books = [_row_to_dict(r, BOOKS_HEADERS) for r in raw_books[start:] if any(c.strip() for c in r)]

    hl_ws = sh.worksheet(HIGHLIGHTS_SHEET)
    raw_hl = hl_ws.get_all_values()
    start = 1 if raw_hl and raw_hl[0][: len(HIGHLIGHTS_HEADERS)] == HIGHLIGHTS_HEADERS else 0
    hls = [_row_to_dict(r, HIGHLIGHTS_HEADERS) for r in raw_hl[start:] if any(c.strip() for c in r)]

    return books, hls


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_per_book(gc, file_id: str, header_and_rows: list[list[str]]) -> None:
    """Replace sheet 1 of ``file_id`` with the supplied rows."""
    sh = gc.open_by_key(file_id)
    ws = sh.sheet1
    ws.clear()
    if header_and_rows:
        ws.update("A1", header_and_rows, value_input_option="RAW")


def main_cli() -> int:
    if not _RUNTIME_DEPS_OK:
        raise SystemExit(
            "Runtime dependencies missing. Install requirements first: "
            "pip install -r requirements/requirements.txt"
        )

    # Local import so tests do not pay the cost of nest_asyncio etc.
    import main as repo_main

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="actually write to Drive (default: dry-run)"
    )
    parser.add_argument(
        "--folder",
        default=DEFAULT_SUBFOLDER_NAME,
        help=f"name of the per-book subfolder (default: {DEFAULT_SUBFOLDER_NAME!r})",
    )
    args = parser.parse_args()

    repo_main.load_config()
    if not repo_main.GOOGLE_SHEETS_ENABLED:
        raise SystemExit(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE and "
            "GOOGLE_SHEETS_SPREADSHEET_ID in config/KEYS.env first."
        )

    creds = _build_creds(repo_main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
    drive = _drive_session(creds)
    gc = gspread.authorize(creds)

    books, highlights = _load_master(gc, repo_main.GOOGLE_SHEETS_SPREADSHEET_ID)
    grouped = group_highlights_by_book(highlights)
    print(f"[master] {len(books)} books, {len(highlights)} highlights")

    parent_id = _get_parent_folder(drive, repo_main.GOOGLE_SHEETS_SPREADSHEET_ID)
    print(f"[parent] folder id = {parent_id}")

    sub_id = _find_or_create_subfolder(drive, parent_id, args.folder, dry_run=not args.apply)
    if sub_id is None:
        print(f"[dry-run] subfolder '{args.folder}' does not exist; would create it.")
    else:
        print(f"[subfolder] '{args.folder}' id = {sub_id}")

    existing = _list_spreadsheets_in_folder(drive, sub_id) if sub_id else {}

    plan_create = 0
    plan_update = 0
    plan_skip = 0

    for book in books:
        bid = book["book_id"].strip()
        title = book["title"].strip()
        if not bid or not title:
            continue
        hl = grouped.get(bid, [])
        if not hl:
            plan_skip += 1
            continue

        fname = per_book_filename(bid, title)
        rows = per_book_rows(hl)
        existing_id = existing.get(fname)

        if existing_id:
            plan_update += 1
            action = "update"
        else:
            plan_create += 1
            action = "create"

        if not args.apply:
            print(f"  [{action:6s}] {fname}  ({len(hl)} highlights)")
            continue

        if existing_id:
            file_id = existing_id
        else:
            file_id = _create_spreadsheet_in_folder(drive, sub_id, fname)
        _write_per_book(gc, file_id, rows)
        print(f"  [{action:6s}] {fname}  ({len(hl)} highlights)  id={file_id}")

    print(
        f"\n[summary] create={plan_create}  update={plan_update}  "
        f"skip(no_highlights)={plan_skip}"
    )
    if not args.apply:
        print("(dry-run) re-run with --apply to write to Drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
