"""Split master ``reading_note`` into fixed NotebookLM volume files.

NotebookLM caps a notebook at 50 sources, so a "one Sheets file per book"
layout breaks at the 51st book. This script instead writes a **fixed**
set of files regardless of how many books exist:

- 49 *volume* files, each holding many books.
- 1 *index* file mapping every book to the volume that contains it.

Total = 50 files, forever. Each book is pinned to a volume by a stable
hash of its ``book_id`` (see ``volume_for_book_id``), so re-runs never
move a book between volumes and the operation is effectively append-only.

It reads the v2 master schema (``01_books`` + ``02_highlights``) and
writes / refreshes the 50 files inside a ``notebooklm/`` subfolder next
to the master spreadsheet.

Usage::

    python -m scripts.split_per_book                   # dry-run
    python -m scripts.split_per_book --apply           # actually write
    python -m scripts.split_per_book --apply --folder notebooklm

Design notes:

- Uses the same Service Account credential as the rest of the pipeline.
- No new external API / AI dependency.  Drive API calls go through
  ``google.auth.transport.requests.AuthorizedSession`` which is already a
  transitive dep of ``google-auth``.
- Idempotent: every volume / index file is rewritten in full from the
  master.  The master itself is **never** modified.
- Filenames are fixed: ``<prefix>_index`` and ``<prefix>_vol_01`` ..
  ``<prefix>_vol_49``.  Service Accounts cannot create Drive files, so the
  user creates these 50 empty Sheets **once**; new books afterwards need
  no new files.
- Each volume row is self-describing (``book_id`` + ``book_title`` on
  every row) so NotebookLM cannot mis-attribute a highlight when a single
  file holds multiple books.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
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

# Fixed layout: 49 volume files + 1 index file = 50 NotebookLM sources.
VOLUME_COUNT = 49
DEFAULT_SUBFOLDER_NAME = "notebooklm"
DEFAULT_FILENAME_PREFIX = "k2n"

# Columns on each volume sheet. ``book_id`` + ``book_title`` make every row
# self-describing so NotebookLM keeps book context even when one file holds
# multiple books.
VOLUME_HEADERS = ["book_id", "book_title", "highlight_id", "location", "content"]

# Columns on the index sheet (book -> volume lookup + catalogue).
INDEX_HEADERS = ["book_id", "title", "volume", "highlight_count", "last_synced_at"]

# Maximum length for the title portion of the index ``title`` column.
TITLE_MAX_LEN = 80


# ---------------------------------------------------------------------------
# Pure helpers (covered by tests)
# ---------------------------------------------------------------------------


def safe_title_for_filename(title: str, max_len: int = TITLE_MAX_LEN) -> str:
    """Strip filesystem-unfriendly chars and collapse whitespace."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len].rstrip()


def volume_for_book_id(book_id: str, volume_count: int = VOLUME_COUNT) -> int:
    """Return the 1-based volume index (1..volume_count) for a book.

    Deterministic across machines and re-runs: ``SHA1(book_id) % N + 1``.
    This formula is load-bearing -- once books have been written, changing
    it (or ``VOLUME_COUNT``) re-shuffles every book and forces a full
    NotebookLM re-import.
    """
    digest = hashlib.sha1((book_id or "").strip().encode("utf-8")).hexdigest()
    return int(digest, 16) % volume_count + 1


def volume_filename(prefix: str, volume_index: int) -> str:
    """``<prefix>_vol_NN`` (no extension; Google Sheets is a native type)."""
    return f"{prefix}_vol_{volume_index:02d}"


def index_filename(prefix: str) -> str:
    """``<prefix>_index`` (no extension)."""
    return f"{prefix}_index"


def all_target_filenames(prefix: str, volume_count: int = VOLUME_COUNT) -> list[str]:
    """The fixed set of file names: the index first, then every volume."""
    return [index_filename(prefix)] + [
        volume_filename(prefix, v) for v in range(1, volume_count + 1)
    ]


def group_books_by_volume(
    books: list[dict], volume_count: int = VOLUME_COUNT
) -> dict[int, list[dict]]:
    """Bucket ``01_books`` row-dicts into volumes 1..volume_count.

    Every volume key is present (empty volumes map to an empty list) so
    callers can iterate the full fixed range. Rows with a blank ``book_id``
    are skipped.
    """
    out: dict[int, list[dict]] = {v: [] for v in range(1, volume_count + 1)}
    for book in books:
        bid = (book.get("book_id") or "").strip()
        if not bid:
            continue
        out[volume_for_book_id(bid, volume_count)].append(book)
    return out


def volume_rows(
    books_in_volume: list[dict], highlights_by_book: dict[str, list[dict]]
) -> list[list[str]]:
    """Header + body for one volume worksheet.

    Books are sorted by ``book_id`` and highlights within a book by
    ``highlight_id`` so the output is byte-stable across re-runs. The
    ``book_title`` comes from the book row (consistent for every row of a
    book); ``location`` falls back to ``page``.
    """
    rows: list[list[str]] = [VOLUME_HEADERS]
    for book in sorted(books_in_volume, key=lambda b: (b.get("book_id") or "").strip()):
        bid = (book.get("book_id") or "").strip()
        btitle = (book.get("title") or "").strip()
        highlights = sorted(
            highlights_by_book.get(bid, []),
            key=lambda h: (h.get("highlight_id") or "").strip(),
        )
        for hl in highlights:
            rows.append(
                [
                    bid,
                    btitle,
                    (hl.get("highlight_id") or "").strip(),
                    (hl.get("location") or hl.get("page") or "").strip(),
                    (hl.get("content") or "").strip(),
                ]
            )
    return rows


def index_rows(
    books: list[dict],
    highlights_by_book: dict[str, list[dict]],
    prefix: str,
    volume_count: int = VOLUME_COUNT,
) -> list[list[str]]:
    """Header + one row per book for the index worksheet.

    ``volume`` is the volume *filename* (more useful than a bare number).
    ``highlight_count`` prefers ``01_books.highlight_count`` and falls back
    to the number of highlights actually grouped for the book.
    """
    rows: list[list[str]] = [INDEX_HEADERS]
    for book in sorted(books, key=lambda b: (b.get("book_id") or "").strip()):
        bid = (book.get("book_id") or "").strip()
        if not bid:
            continue
        count = (book.get("highlight_count") or "").strip()
        if not count:
            count = str(len(highlights_by_book.get(bid, [])))
        rows.append(
            [
                bid,
                safe_title_for_filename(book.get("title") or ""),
                volume_filename(prefix, volume_for_book_id(bid, volume_count)),
                count,
                (book.get("last_synced_at") or "").strip(),
            ]
        )
    return rows


def group_highlights_by_book(highlight_rows: list[dict]) -> dict[str, list[dict]]:
    """Group highlight dicts by book_id, preserving original ordering."""
    out: dict[str, list[dict]] = {}
    for row in highlight_rows:
        bid = (row.get("book_id") or "").strip()
        if not bid:
            continue
        out.setdefault(bid, []).append(row)
    return out


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
            f"Master spreadsheet {file_id} appears to live in 'My Drive' root "
            "and its parent folder cannot be determined via the Drive API. "
            "Either move it into a folder, or pass --parent-folder <folder_id> "
            "to specify the destination folder directly."
        )
    return parents[0]


def _validate_parent_folder(drive: AuthorizedSession, folder_id: str) -> None:
    """Ensure ``folder_id`` is an accessible folder the service account can write to."""
    r = drive.get(
        f"{DRIVE_API}/files/{folder_id}",
        params={"fields": "id,name,mimeType,capabilities(canAddChildren)"},
    )
    if r.status_code == 404:
        raise SystemExit(
            f"--parent-folder {folder_id!r} not found. "
            "Check the ID, and make sure the folder is shared with the service account."
        )
    if r.status_code == 403:
        raise SystemExit(
            f"Service account cannot access folder {folder_id!r}. "
            "Open the folder in Google Drive, click 'Share', and add the service "
            "account email with Editor permission."
        )
    r.raise_for_status()
    info = r.json()
    mime = info.get("mimeType")
    if mime != "application/vnd.google-apps.folder":
        raise SystemExit(
            f"--parent-folder {folder_id!r} points to "
            f"{info.get('name', '?')!r} with mimeType={mime!r}, not a folder. "
            "Pass a folder ID (find it in the URL when you open the folder: "
            "drive.google.com/drive/folders/<FOLDER_ID>), not a spreadsheet/file ID."
        )
    if not info.get("capabilities", {}).get("canAddChildren", False):
        raise SystemExit(
            f"Service account lacks permission to create files in folder "
            f"{info.get('name', folder_id)!r}. Share the folder with the "
            "service account email and grant Editor access."
        )


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


def _write_volume(gc, file_id: str, header_and_rows: list[list[str]]) -> None:
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
        help=f"name of the destination subfolder (default: {DEFAULT_SUBFOLDER_NAME!r})",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_FILENAME_PREFIX,
        help=(
            "filename prefix for the volume / index files "
            f"(default: {DEFAULT_FILENAME_PREFIX!r}; produces "
            f"'{DEFAULT_FILENAME_PREFIX}_index' and "
            f"'{DEFAULT_FILENAME_PREFIX}_vol_01'..)"
        ),
    )
    parser.add_argument(
        "--parent-folder",
        metavar="FOLDER_ID",
        default=None,
        help=(
            "Google Drive folder ID to create the destination subfolder inside. "
            "Use this when the master spreadsheet lives in 'My Drive' root and "
            "the Drive API cannot determine its parent automatically. "
            "Find the ID in the folder's URL: "
            "drive.google.com/drive/folders/<FOLDER_ID>"
        ),
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
    highlights_by_book = group_highlights_by_book(highlights)
    books_by_volume = group_books_by_volume(books)
    print(f"[master] {len(books)} books, {len(highlights)} highlights")
    print(
        f"[layout] {VOLUME_COUNT} volumes + 1 index = {VOLUME_COUNT + 1} files, "
        f"prefix '{args.prefix}'"
    )

    if args.parent_folder:
        parent_id = args.parent_folder
        _validate_parent_folder(drive, parent_id)
        print(f"[parent] folder id = {parent_id}  (from --parent-folder)")
    else:
        parent_id = _get_parent_folder(drive, repo_main.GOOGLE_SHEETS_SPREADSHEET_ID)
        print(f"[parent] folder id = {parent_id}")

    sub_id = _find_or_create_subfolder(drive, parent_id, args.folder, dry_run=not args.apply)
    if sub_id is None:
        print(f"[dry-run] subfolder '{args.folder}' does not exist; would create it.")
    else:
        print(f"[subfolder] '{args.folder}' id = {sub_id}")

    existing = _list_spreadsheets_in_folder(drive, sub_id) if sub_id else {}

    # Build the fixed set of (filename, rows, label) targets: index first.
    targets: list[tuple[str, list[list[str]], str]] = [
        (
            index_filename(args.prefix),
            index_rows(books, highlights_by_book, args.prefix),
            f"{len(books)} books",
        )
    ]
    for v in range(1, VOLUME_COUNT + 1):
        vbooks = books_by_volume[v]
        nhl = sum(len(highlights_by_book.get((b.get("book_id") or "").strip(), [])) for b in vbooks)
        targets.append(
            (
                volume_filename(args.prefix, v),
                volume_rows(vbooks, highlights_by_book),
                f"{len(vbooks)} books, {nhl} highlights",
            )
        )

    plan_update = 0
    plan_missing = 0
    missing_filenames: list[str] = []

    for fname, rows, label in targets:
        existing_id = existing.get(fname)
        if existing_id:
            plan_update += 1
            if args.apply:
                _write_volume(gc, existing_id, rows)
                print(f"  [update ] {fname}  ({label})  id={existing_id}")
            else:
                print(f"  [update ] {fname}  ({label})")
        else:
            plan_missing += 1
            missing_filenames.append(fname)
            tag = "missing" if args.apply else "create "
            print(f"  [{tag}] {fname}  ({label})")

    volume_book_counts = [len(books_by_volume[v]) for v in range(1, VOLUME_COUNT + 1)]
    print(
        f"\n[distribution] books per volume -- min={min(volume_book_counts)} "
        f"median={statistics.median(volume_book_counts):g} "
        f"max={max(volume_book_counts)}"
    )
    print(f"[summary] update={plan_update}  missing={plan_missing}")

    if missing_filenames:
        print(
            f"\n{plan_missing} of the {VOLUME_COUNT + 1} fixed file(s) are not yet "
            f"in the '{args.folder}' folder. Create them ONCE, manually, as Google "
            "Sheets with these EXACT names (no extension):"
        )
        for f in missing_filenames:
            print(f"  - {f}")
        print(
            "\nThen re-run the script. Once all "
            f"{VOLUME_COUNT + 1} files exist, new books never need new files."
        )
    if not args.apply:
        print("\n(dry-run) re-run with --apply to write content to existing files.")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
