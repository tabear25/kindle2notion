"""Split master ``reading_note`` into fixed NotebookLM volume files.

NotebookLM caps a notebook at 50 sources, so a "one Sheets file per book"
layout breaks at the 51st book. This script instead writes a **fixed**
set of files regardless of how many books exist:

- 49 *volume* files, each holding many books.
- 1 *index* file mapping every book to the volume that contains it.

Total = 50 files, forever. Each book is pinned to a volume by a stable
hash of its ``book_id`` (see ``volume_for_book_id``), so re-runs never
move a book between volumes and the operation is effectively append-only.

These 50 files are now the **single source of truth** for highlights. The
primary write path is :func:`sync_notes_to_notebooklm`, which merges scraped /
manual notes directly into the volume + index files (called automatically after
a Kindle scrape from ``main.py`` / ``web/pipeline.py`` and after a manual add
from ``scripts/add_manual_highlights.py``). The retired ``01_books`` /
``02_highlights`` master is **no longer written**; it is only read by the
legacy ``--from-master`` CLI backfill below.

CLI usage::

    python -m scripts.split_per_book                   # dry-run: rebuild index from volumes
    python -m scripts.split_per_book --apply           # rebuild k2n_index from the 49 volumes
    python -m scripts.split_per_book --from-master --apply  # LEGACY: re-split from the retired master

Writes are paced (and retried on a per-minute 429) so a full 50-file ``--apply``
completes in one run. If the destination folder's Drive parent cannot be
auto-resolved (e.g. it sits in 'My Drive' root or inside a trashed folder), set
the ``NOTEBOOKLM_PARENT_FOLDER_ID`` env var (or pass ``--parent-folder``) so the
destination folder is found without it.

Design notes:

- Uses the same Service Account credential as the rest of the pipeline.
- No new external API / AI dependency.  Drive API calls go through
  ``google.auth.transport.requests.AuthorizedSession`` which is already a
  transitive dep of ``google-auth``.
- Each volume file is **self-describing** (every row carries ``book_id`` +
  ``book_title``), so :func:`sync_notes_to_notebooklm` reconstructs a volume's
  existing state from the volume itself -- never from the lossy index -- when
  merging in new highlights.
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
import os
import re
import statistics
import sys
import time
from pathlib import Path

# Make the project root importable when run as ``python scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ``note_utils`` is pure standard library (no gspread / google-auth), so it
# imports cleanly even when the heavy runtime deps below are missing. The merge
# + id helpers depend on it and must stay importable for the unit tests, so it
# is imported UNCONDITIONALLY (outside the guarded block).
from note_utils import (  # noqa: E402
    BOOKS_HEADERS,
    HIGHLIGHTS_HEADERS,
    content_dedup_key,
    highlight_id,
    normalize_text,
    stable_book_id,
    today_iso,
)

# Heavy runtime imports are guarded so that unit tests can import the pure
# helpers without needing gspread / google-auth / nest_asyncio installed.
try:
    import gspread  # type: ignore
    from gspread.exceptions import APIError  # type: ignore
    from google.auth.transport.requests import AuthorizedSession  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
    from google_sheets.toSheets import BOOKS_SHEET, HIGHLIGHTS_SHEET, SCOPES  # noqa: E402
    _RUNTIME_DEPS_OK = True
except Exception:  # pragma: no cover -- only hit during test collection
    _RUNTIME_DEPS_OK = False

DRIVE_API = "https://www.googleapis.com/drive/v3"

# Fixed layout: 49 volume files + 1 index file = 50 NotebookLM sources.
VOLUME_COUNT = 49
DEFAULT_SUBFOLDER_NAME = "notebooklm"
DEFAULT_FILENAME_PREFIX = "k2n"

# Google Sheets caps writes at ~60 requests/min/user. Each volume rewrite is
# clear()+update() = 2 write requests, and a full run touches all 50 files
# (~100 requests), so an unthrottled ``--apply`` reliably trips a 429 partway
# through and leaves the later volumes stale. Pace each write to stay under the
# limit, and retry once the per-minute window resets (see ``_write_volume``).
WRITE_THROTTLE_SECONDS = 2.5
QUOTA_RETRY_WAIT_SECONDS = 60
MAX_QUOTA_RETRIES = 5

# Env var naming the Drive folder that hosts the ``notebooklm`` subfolder. Set
# this when the master spreadsheet's own parent cannot be auto-resolved (e.g.
# the master lives in 'My Drive' root, or has been moved into a trashed folder),
# so ``--apply`` no longer needs the ``--parent-folder`` flag each run.
PARENT_FOLDER_ENV_VAR = "NOTEBOOKLM_PARENT_FOLDER_ID"

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


def _strip_header(rows: list[list[str]], headers: list[str]) -> list[list[str]]:
    """Drop a leading header row if it matches ``headers``; return the body."""
    body = list(rows or [])
    if body and list(body[0][: len(headers)]) == headers:
        body = body[1:]
    return [r for r in body if any((c or "").strip() for c in r)]


def _volume_row_to_highlight(row: list[str]) -> dict:
    """Inverse of one ``volume_rows`` body row -> a highlight dict.

    Pads short rows and strips whitespace so a round-trip
    (``volume_rows`` -> parse -> ``volume_rows``) is byte-stable.
    """
    padded = (list(row) + [""] * len(VOLUME_HEADERS))[: len(VOLUME_HEADERS)]
    d = dict(zip(VOLUME_HEADERS, padded))
    return {key: (d.get(key) or "").strip() for key in VOLUME_HEADERS}


def _index_row_to_book(row: list[str]) -> dict:
    """Inverse of one ``index_rows`` body row -> a book dict."""
    padded = (list(row) + [""] * len(INDEX_HEADERS))[: len(INDEX_HEADERS)]
    d = dict(zip(INDEX_HEADERS, padded))
    return {key: (d.get(key) or "").strip() for key in INDEX_HEADERS}


def volumes_for_book_ids(book_ids, volume_count: int = VOLUME_COUNT) -> set:
    """Return the set of volume indices touched by a collection of book_ids.

    Blank ids are ignored. Two book_ids hashing to the same volume collapse to
    one entry, so this is the minimal set of volume files a sync must read/write.
    """
    return {
        volume_for_book_id(bid, volume_count)
        for bid in book_ids
        if (bid or "").strip()
    }


def merge_notes_into_volume(
    volume_rows_in: list[list[str]],
    notes_for_volume: list[dict],
    *,
    today: str | None = None,
):
    """Merge ``notes_for_volume`` into one volume file's existing rows.

    ``volume_rows_in`` is the volume sheet's ``get_all_values()`` output (header
    + body, or empty); ``notes_for_volume`` are the note dicts whose book maps to
    this volume. Returns ``(new_rows, summary, touched_book_ids, book_meta)``:

    - ``new_rows``   -- the full replacement sheet content (header + body),
      rebuilt via :func:`volume_rows` so it is sorted + byte-stable.
    - ``summary``    -- the 5 standard counters (same keys as
      ``toSheets.save_notes_to_google_sheets``).
    - ``touched``    -- book_ids that gained a highlight or are brand new.
    - ``book_meta``  -- ``{book_id: {"title", "count"}}`` for every book in the
      rewritten volume (used to refresh the index without re-reading).

    Pure: no I/O. Because each volume row carries its own ``book_id`` +
    ``book_title``, existing highlights, titles and per-book ``highlight_id``
    numbering are reconstructed from the rows themselves -- never from the lossy
    (truncated/sanitised) index.
    """
    today = today or today_iso()

    existing_highlights: list[dict] = []
    titles: dict[str, str] = {}
    for raw in _strip_header(volume_rows_in, VOLUME_HEADERS):
        hl = _volume_row_to_highlight(raw)
        bid = hl["book_id"]
        if not bid:
            continue
        existing_highlights.append(hl)
        if hl["book_title"] and bid not in titles:
            titles[bid] = hl["book_title"]

    dedup: set = set()
    max_idx: dict[str, int] = {}
    for hl in existing_highlights:
        bid = hl["book_id"]
        content = hl["content"]
        if bid and content:
            dedup.add(content_dedup_key(bid, content))
        hid = hl["highlight_id"]
        if hid.startswith("HL-") and "-" in hid[3:]:
            tail = hid.rsplit("-", 1)[-1]
            if tail.isdigit() and int(tail) > max_idx.get(bid, 0):
                max_idx[bid] = int(tail)

    new_books = 0
    new_highlights = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    touched: set = set()
    appended: list[dict] = []

    for note in notes_for_volume:
        title = normalize_text(note.get("title"))
        content = normalize_text(note.get("content"))
        if not title or not content:
            skipped_invalid += 1
            continue
        bid = (note.get("book_id") or "").strip() or stable_book_id(title)
        if bid not in titles:
            titles[bid] = title
            new_books += 1
            touched.add(bid)
        key = content_dedup_key(bid, content)
        if key in dedup:
            skipped_duplicates += 1
            continue
        max_idx[bid] = max_idx.get(bid, 0) + 1
        supplied_idx = note.get("idx_within_book")
        if isinstance(supplied_idx, int) and supplied_idx > max_idx[bid]:
            max_idx[bid] = supplied_idx
        hid = highlight_id(bid, max_idx[bid])
        appended.append(
            {
                "book_id": bid,
                "book_title": titles[bid],
                "highlight_id": hid,
                "location": normalize_text(note.get("location") or note.get("page")),
                "content": content,
            }
        )
        dedup.add(key)
        new_highlights += 1
        touched.add(bid)

    all_highlights = existing_highlights + appended
    books_in_vol = [{"book_id": bid, "title": titles.get(bid, "")} for bid in titles]
    highlights_by_book = group_highlights_by_book(all_highlights)
    new_rows = volume_rows(books_in_vol, highlights_by_book)

    book_meta = {
        bid: {"title": titles.get(bid, ""), "count": len(highlights_by_book.get(bid, []))}
        for bid in titles
    }
    summary = {
        "new_books": new_books,
        "new_highlights": new_highlights,
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
        "total_notes": len(notes_for_volume),
    }
    return new_rows, summary, touched, book_meta


_SUMMARY_KEYS = (
    "new_books",
    "new_highlights",
    "skipped_duplicates",
    "skipped_invalid",
    "total_notes",
)


def merge_summaries(summaries) -> dict:
    """Sum the 5 standard counter keys across a list of per-volume summaries."""
    out = {key: 0 for key in _SUMMARY_KEYS}
    for summary in summaries:
        for key in _SUMMARY_KEYS:
            out[key] += int(summary.get(key, 0) or 0)
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
    """Replace sheet 1 of ``file_id`` with the supplied rows.

    Paces each write and retries on a per-minute write-quota error (HTTP 429)
    so a full 50-file ``--apply`` completes in one run instead of dying partway
    through and leaving the later volumes stale.
    """
    sh = gc.open_by_key(file_id)
    ws = sh.sheet1
    for attempt in range(MAX_QUOTA_RETRIES + 1):
        try:
            ws.clear()
            if header_and_rows:
                ws.update("A1", header_and_rows, value_input_option="RAW")
            break
        except APIError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 429 and attempt < MAX_QUOTA_RETRIES:
                print(
                    f"  [quota] write-rate limit (429); waiting "
                    f"{QUOTA_RETRY_WAIT_SECONDS}s then retrying "
                    f"({attempt + 1}/{MAX_QUOTA_RETRIES})...",
                    flush=True,
                )
                time.sleep(QUOTA_RETRY_WAIT_SECONDS)
                continue
            raise
    if WRITE_THROTTLE_SECONDS:
        time.sleep(WRITE_THROTTLE_SECONDS)


def _read_volume(gc, file_id: str) -> list[list[str]]:
    """Return ``get_all_values()`` of sheet 1 of ``file_id`` (header + body)."""
    return gc.open_by_key(file_id).sheet1.get_all_values()


def _resolve_notebooklm_folder(
    drive,
    *,
    spreadsheet_id: str | None = None,
    parent_folder_id: str | None = None,
    folder: str = DEFAULT_SUBFOLDER_NAME,
):
    """Resolve the folder that holds the 50 files + the spreadsheets in it.

    Resolution order for the configured folder: explicit ``parent_folder_id`` ->
    ``NOTEBOOKLM_PARENT_FOLDER_ID`` env var -> the (legacy) master spreadsheet's
    own Drive parent, only when ``spreadsheet_id`` is supplied.

    The configured folder may be **either** the parent that contains a ``folder``
    subfolder (e.g. ``notebooklm/``) **or** the folder that holds the 50 files
    *directly*. We first look for a ``folder`` subfolder; if there isn't one, we
    use the configured folder itself. So ``NOTEBOOKLM_PARENT_FOLDER_ID`` can point
    straight at the folder containing the 50 files (the intuitive setting).

    Returns ``(sub_id, {filename: file_id})``.
    """
    env_parent = os.environ.get(PARENT_FOLDER_ENV_VAR, "").strip()
    if parent_folder_id:
        parent_id = parent_folder_id
        _validate_parent_folder(drive, parent_id)
    elif env_parent:
        parent_id = env_parent
        _validate_parent_folder(drive, parent_id)
    elif spreadsheet_id:
        parent_id = _get_parent_folder(drive, spreadsheet_id)
    else:
        raise SystemExit(
            "Cannot locate the NotebookLM destination folder. Set "
            f"{PARENT_FOLDER_ENV_VAR} in config/KEYS.env to the Drive folder ID "
            "that holds the 50 files (or its parent)."
        )
    sub_id = _find_or_create_subfolder(drive, parent_id, folder, dry_run=True)
    if sub_id is None:
        # No ``folder`` subfolder -> the configured folder IS the destination
        # (the 50 files live directly in it). Use it as-is.
        sub_id = parent_id
    existing = _list_spreadsheets_in_folder(drive, sub_id)
    return sub_id, existing


def sync_notes_to_notebooklm(
    notes,
    *,
    apply: bool = True,
    progress_callback=None,
    prefix: str = DEFAULT_FILENAME_PREFIX,
    folder: str = DEFAULT_SUBFOLDER_NAME,
    parent_folder_id: str | None = None,
) -> dict:
    """Merge scraped / manual notes directly into the NotebookLM 50-file layout.

    This is the source-of-truth writer that replaced the retired ``01_books`` /
    ``02_highlights`` master. For each volume the incoming notes touch (a book is
    pinned to one volume by :func:`volume_for_book_id`), it reads that volume
    back, merges new highlights (dedup by content, continuing the per-book
    ``highlight_id`` numbering), and rewrites the volume; then it refreshes the
    index. Only touched volumes + the index are written, so a normal incremental
    scrape stays well inside the Sheets write quota.

    Files absent from the folder are reported in ``missing_files`` (service
    accounts cannot create Drive files), and their highlights are NOT written.

    Returns ``{new_books, new_highlights, skipped_duplicates, skipped_invalid,
    total_notes, missing_files, touched_volumes}``. Progress is reported under
    the existing ``"sheets"`` phase, one tick per file written.
    """
    if not _RUNTIME_DEPS_OK:
        raise SystemExit(
            "Runtime dependencies missing. Install requirements first: "
            "pip install -r requirements/requirements.txt"
        )

    notes = list(notes)
    summary = {
        "new_books": 0,
        "new_highlights": 0,
        "skipped_duplicates": 0,
        "skipped_invalid": 0,
        "total_notes": len(notes),
        "missing_files": [],
        "touched_volumes": 0,
    }
    if not notes:
        return summary

    # Local import (deferred) so importing this module stays cheap and there is
    # no import-time cycle with ``main`` (which imports this module lazily too).
    import main as repo_main

    repo_main.load_config()
    if not repo_main.GOOGLE_SHEETS_ENABLED:
        raise SystemExit(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE "
            "and GOOGLE_SHEETS_SPREADSHEET_ID in config/KEYS.env first."
        )

    creds = _build_creds(repo_main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE)
    drive = _drive_session(creds)
    gc = gspread.authorize(creds)

    sub_id, existing = _resolve_notebooklm_folder(
        drive,
        spreadsheet_id=repo_main.GOOGLE_SHEETS_SPREADSHEET_ID,
        parent_folder_id=parent_folder_id,
        folder=folder,
    )

    today = today_iso()

    # Route each valid note to its volume; pre-count blank ones as invalid so we
    # never read/write a volume just to drop a degenerate note.
    notes_by_volume: dict[int, list[dict]] = {}
    prefiltered_invalid = 0
    for note in notes:
        title = normalize_text(note.get("title"))
        content = normalize_text(note.get("content"))
        if not title or not content:
            prefiltered_invalid += 1
            continue
        bid = (note.get("book_id") or "").strip() or stable_book_id(title)
        notes_by_volume.setdefault(volume_for_book_id(bid), []).append(note)

    affected = sorted(notes_by_volume)
    total_files = len(affected) + 1  # + index
    if len(affected) > 20:
        print(
            f"[notebooklm] {len(affected)} volumes affected; this run issues "
            f"~{total_files * 2} write requests and may take a few minutes "
            "(paced to stay under the Sheets quota).",
            flush=True,
        )

    summaries: list[dict] = []
    missing_files: list[str] = []
    touched_all: set = set()
    book_meta: dict[str, dict] = {}
    written = 0

    for i, volume in enumerate(affected):
        fname = volume_filename(prefix, volume)
        file_id = existing.get(fname)
        if not file_id:
            missing_files.append(fname)
            if progress_callback:
                progress_callback("sheets", i + 1, total_files, f"{fname} [missing]")
            continue
        new_rows, vol_summary, touched, vol_book_meta = merge_notes_into_volume(
            _read_volume(gc, file_id), notes_by_volume[volume], today=today
        )
        summaries.append(vol_summary)
        touched_all |= touched
        book_meta.update(vol_book_meta)
        if apply:
            _write_volume(gc, file_id, new_rows)
            written += 1
        if progress_callback:
            progress_callback("sheets", i + 1, total_files, fname)

    # Refresh the index ONLY for touched books (gained a highlight / new book),
    # preserving every untouched row -- so an untouched book keeps its stored
    # highlight_count + last_synced_at.
    index_fname = index_filename(prefix)
    index_id = existing.get(index_fname)
    if not index_id:
        missing_files.append(index_fname)
    elif touched_all:
        books_by_id: dict[str, dict] = {}
        for raw in _strip_header(_read_volume(gc, index_id), INDEX_HEADERS):
            book = _index_row_to_book(raw)
            if book["book_id"]:
                books_by_id[book["book_id"]] = book
        for bid in touched_all:
            meta = book_meta.get(bid)
            if not meta:
                continue
            books_by_id[bid] = {
                "book_id": bid,
                "title": meta["title"],
                "highlight_count": str(meta["count"]),
                "last_synced_at": today,
            }
        index_new_rows = index_rows(list(books_by_id.values()), {}, prefix)
        if apply:
            _write_volume(gc, index_id, index_new_rows)
        if progress_callback:
            progress_callback("sheets", total_files, total_files, index_fname)

    final = merge_summaries(summaries)
    final["skipped_invalid"] += prefiltered_invalid
    final["total_notes"] = len(notes)
    final["missing_files"] = missing_files
    final["touched_volumes"] = written
    return final


def list_books_from_index(
    service_account_file,
    spreadsheet_id: str | None = None,
    *,
    parent_folder_id: str | None = None,
    prefix: str = DEFAULT_FILENAME_PREFIX,
    folder: str = DEFAULT_SUBFOLDER_NAME,
) -> list[dict]:
    """Read existing books from the NotebookLM ``<prefix>_index`` file.

    Read-only replacement for ``toSheets.list_existing_books`` now that the
    master is retired. Returns ``[{book_id, title, author, highlight_count}]``
    sorted by title (``author`` is always ``""`` -- the index carries no author
    column; title matching only needs the title). Returns ``[]`` when the index
    file is missing.
    """
    if not _RUNTIME_DEPS_OK:
        raise SystemExit(
            "Runtime dependencies missing. Install requirements first: "
            "pip install -r requirements/requirements.txt"
        )
    creds = _build_creds(service_account_file)
    drive = _drive_session(creds)
    gc = gspread.authorize(creds)

    _sub_id, existing = _resolve_notebooklm_folder(
        drive, spreadsheet_id=spreadsheet_id, parent_folder_id=parent_folder_id, folder=folder
    )
    index_id = existing.get(index_filename(prefix))
    if not index_id:
        return []

    out: list[dict] = []
    for raw in _strip_header(_read_volume(gc, index_id), INDEX_HEADERS):
        book = _index_row_to_book(raw)
        if not book["book_id"] or not book["title"]:
            continue
        out.append(
            {
                "book_id": book["book_id"],
                "title": book["title"],
                "author": "",
                "highlight_count": book["highlight_count"],
            }
        )
    out.sort(key=lambda b: b["title"])
    return out


def _rebuild_index_from_volumes(gc, existing: dict, prefix: str) -> list[list[str]]:
    """Rebuild the index rows from the 49 volume files (volumes = source of truth).

    Volumes are self-describing, so the full catalogue (book_id, title,
    highlight_count) is recoverable without the retired master. ``last_synced_at``
    is left blank because volumes do not record it. Returns the header + body
    rows for the index sheet.
    """
    books_by_id: dict[str, dict] = {}
    for volume in range(1, VOLUME_COUNT + 1):
        file_id = existing.get(volume_filename(prefix, volume))
        if not file_id:
            continue
        for raw in _strip_header(_read_volume(gc, file_id), VOLUME_HEADERS):
            hl = _volume_row_to_highlight(raw)
            bid = hl["book_id"]
            if not bid:
                continue
            book = books_by_id.setdefault(
                bid, {"book_id": bid, "title": hl["book_title"], "_count": 0, "last_synced_at": ""}
            )
            book["_count"] += 1
            if hl["book_title"] and not book["title"]:
                book["title"] = hl["book_title"]
    for book in books_by_id.values():
        book["highlight_count"] = str(book.pop("_count"))
    return index_rows(list(books_by_id.values()), {}, prefix)


def _cli_from_master(gc, existing: dict, repo_main, args) -> int:
    """LEGACY: re-split all 50 files from the retired master. OVERWRITES everything.

    Highlights now flow into the volumes directly via
    :func:`sync_notes_to_notebooklm`, so the master is normally never read. This
    path exists only for a one-time backfill from an old master and clobbers any
    highlights added to the volumes since the master was last updated.
    """
    print(
        "\n[WARNING] --from-master reads the RETIRED 01_books/02_highlights master "
        "and OVERWRITES all 50 NotebookLM files with it. Any highlights added to the "
        "volumes after the master was last updated will be LOST. Use only for a "
        "one-time backfill.\n",
        flush=True,
    )
    books, highlights = _load_master(gc, repo_main.GOOGLE_SHEETS_SPREADSHEET_ID)
    highlights_by_book = group_highlights_by_book(highlights)
    books_by_volume = group_books_by_volume(books)
    print(f"[master] {len(books)} books, {len(highlights)} highlights")
    print(
        f"[layout] {VOLUME_COUNT} volumes + 1 index = {VOLUME_COUNT + 1} files, "
        f"prefix '{args.prefix}'"
    )

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


def _cli_rebuild_index(gc, existing: dict, args) -> int:
    """Default CLI mode: rebuild ``<prefix>_index`` from the 49 volume files.

    Safe -- it never reads the retired master and never overwrites a volume; it
    only regenerates the index catalogue from the volumes (the source of truth).
    Useful to recover/refresh the index outside the automatic sync.
    """
    print(
        "[mode] rebuild index from the volume files "
        "(the retired master is NOT read; use --from-master for the legacy backfill)"
    )
    index_fname = index_filename(args.prefix)
    index_id = existing.get(index_fname)
    rows = _rebuild_index_from_volumes(gc, existing, args.prefix)
    book_count = max(len(rows) - 1, 0)

    if not index_id:
        print(
            f"  [missing] {index_fname}  ({book_count} books) -- "
            "create it once as a Google Sheet with that exact name, then re-run."
        )
        return 0
    if args.apply:
        _write_volume(gc, index_id, rows)
        print(f"  [update ] {index_fname}  ({book_count} books)  id={index_id}")
    else:
        print(f"  [update ] {index_fname}  ({book_count} books)")
        print("\n(dry-run) re-run with --apply to rewrite the index file.")
    return 0


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
            "drive.google.com/drive/folders/<FOLDER_ID>. "
            f"For a persistent setting, set the {PARENT_FOLDER_ENV_VAR} env var "
            "instead (this flag overrides it)."
        ),
    )
    parser.add_argument(
        "--from-master",
        action="store_true",
        help=(
            "LEGACY: re-split all 50 files from the retired 01_books/02_highlights "
            "master. Highlights now flow into the volumes directly (via "
            "sync_notes_to_notebooklm), so the master is normally NOT read. Only use "
            "this for a one-time backfill -- it OVERWRITES all 50 files and clobbers "
            "any highlights added after the master was last updated. Without this "
            "flag the default action rebuilds only the index from the volumes."
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

    # Resolve the destination folder (same logic + fallback as the sync path:
    # the configured folder may be the parent of a `notebooklm/` subfolder, or
    # the folder that holds the 50 files directly).
    sub_id, existing = _resolve_notebooklm_folder(
        drive,
        spreadsheet_id=repo_main.GOOGLE_SHEETS_SPREADSHEET_ID,
        parent_folder_id=args.parent_folder,
        folder=args.folder,
    )
    print(f"[folder] destination folder id = {sub_id}  ({len(existing)} spreadsheets present)")

    if args.from_master:
        return _cli_from_master(gc, existing, repo_main, args)
    return _cli_rebuild_index(gc, existing, args)


if __name__ == "__main__":
    sys.exit(main_cli())
