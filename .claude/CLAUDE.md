# CLAUDE.md
 
This file provides guidance for AI assistants working on the kindle2notion codebase.
 
## Project Overview
 
kindle2notion is a Python automation tool that scrapes Kindle highlights from the Amazon Kindle notebook page (Japan: `read.amazon.co.jp/notebook`) and exports them to a Notion database. Optionally, highlights can also be exported to Google Sheets.
 
The application uses Playwright for browser automation, the official Notion Python SDK, and a Tkinter-based GUI for user interaction (book limit selection, 2FA code entry).
 
## Repository Structure
 
```
kindle2notion/
├── main.py                         # Application entry point and orchestrator (GUI mode)
├── web_main.py                     # Entry point for Flask web server
├── note_utils.py                   # Shared helpers: legacy dedup keys + v2 ID/row builders
├── __init__.py                     # Package marker
├── amazon/
│   ├── __init__.py
│   └── login.py                    # Amazon authentication via Playwright
├── book_transformer/
│   ├── __init__.py
│   └── transformer.py              # Kindle highlight extraction logic
├── config/
│   ├── __init__.py                 # BASE_DIR, CONFIG_DIR, load_env_file()
│   └── KEYS.env                    # Credentials file (git-ignored, must be created manually)
├── google_sheets/
│   ├── __init__.py
│   └── toSheets.py                 # Google Sheets export (v2 multi-sheet schema)
├── gui_utils/
│   ├── __init__.py
│   └── gui.py                      # Tkinter GUI dialogs + ProgressWindow
├── notion/
│   ├── __init__.py
│   └── toNotion.py                 # Notion database export module
├── scripts/
│   ├── __init__.py
│   ├── migrate_legacy_sheet.py     # One-shot migration: legacy Sheet1 -> v2 schema
│   └── split_per_book.py           # Split master into 49 volume Sheets + 1 index for NotebookLM
├── web/
│   ├── __init__.py
│   ├── app.py                      # Flask application factory (routes, SSE, Basic auth)
│   └── pipeline.py                 # PipelineState + run_pipeline for the web worker thread
├── requirements/
│   └── requirements.txt            # Python package dependencies
└── test/
    ├── test_note_utils.py          # pytest tests for note_utils (legacy + v2 helpers)
    ├── test_split_per_book.py      # pytest tests for scripts/split_per_book.py pure helpers
    └── test_amazon/
        └── test_login.py           # pytest tests for amazon/login.py
```
 
## Setup and Running
 
### Prerequisites
 
- Python 3.11+
- Playwright Chromium browser
 
### Installation
 
```bash
pip install -r requirements/requirements.txt
playwright install chromium
```
 
### Configuration
 
Create `config/KEYS.env` with the following variables:
 
```env
# Required
AMAZON_EMAIL=your@email.com
AMAZON_PASSWORD=yourpassword
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=...
 
# Optional — enable Google Sheets export by setting both
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
GOOGLE_SHEETS_SPREADSHEET_ID=...
 
# Optional — Basic auth for the web UI (omit to disable auth)
WEB_USERNAME=
WEB_PASSWORD=
 
# Optional — web server bind address/port (defaults: 0.0.0.0 / 5000)
WEB_HOST=127.0.0.1
WEB_PORT=5000
```
 
`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` can be either a file path or a raw JSON string starting with `{`.
`GOOGLE_SHEETS_WORKSHEET_NAME` is no longer read; worksheet names are fixed by the v2 schema (`01_books` / `02_highlights`).
 
### Running the Application
 
**GUI mode (Tkinter):**
```bash
python main.py
```
Shows a progress window with per-phase progress bars. 2FA is handled via a Tkinter dialog spawned on the main thread while the Playwright worker thread blocks.
 
**Web mode (Flask):**
```bash
python web_main.py
```
Starts a Flask server on port 5000 (default). Progress is streamed to the browser via Server-Sent Events. 2FA code entry is available on the web UI. See `deploy/README.md` for VPS deployment with Caddy + DuckDNS.
 
Both modes share the same pipeline:
1. Enter the number of books to process (or leave blank for all)
2. Non-headless Chromium opens for Amazon login; 2FA handled if prompted
3. Browser session saved to `storage_state.json`
4. Headless browser scrapes highlights
5. Saves to Notion (always) and Google Sheets (if configured)
 
## Running Tests
 
```bash
pytest test/
```
 
Tests use pytest with monkeypatching. There is no separate test runner script. The test directory is git-ignored, so tests exist only locally.
 
## Application Flow
 
**GUI mode (`python main.py`):**
```
main.py __main__
  └── load_config()                 # Load/validate KEYS.env once
  └── prompt_book_limit()           # Tkinter: ask how many books to process
  └── ProgressWindow.run()          # Tkinter main loop (blocks until done/error)
        worker thread:
          └── run(playwright, max_books, progress_callback, two_factor_callback)
                ├── perform_login()           # Non-headless: login, handle 2FA
                ├── context.storage_state()   # Save session to storage_state.json
                └── extract_notes()           # Headless: scrape highlights
          └── toNotion.save_notes_to_notion()
          └── toSheets.save_notes_to_google_sheets()  # Only if GOOGLE_SHEETS_ENABLED
```
 
**Web mode (`python web_main.py`):**
```
web_main.py
  └── create_app()                  # Flask factory: load config, register routes
        /api/start  POST            # Spawns worker thread, returns immediately
          worker thread:
            └── run_pipeline(state, max_books)
                  └── main.run()   # headless_login=True
                  └── toNotion.save_notes_to_notion()
                  └── toSheets.save_notes_to_google_sheets()
        /api/2fa    POST            # Unblocks the waiting Playwright thread
        /api/events GET (SSE)       # Streams progress events to browser
```
 
## Core Data Structure
 
All modules pass highlights around as a list of dictionaries:
 
```python
{
    "title": "Book Title",   # str: book title from h3 element
    "content": "...",        # str: highlight text
    "page": "42",            # str: page number extracted via regex (may be "")
    # Optional fields (not set by transformer; may be added by future scrapers):
    "book_id": "BK-ABCDEF",  # str: stable id from note_utils.stable_book_id()
    "location": "...",       # str: Kindle location string (preferred over page in Sheets v2)
    "highlighted_at": "",    # str: ISO date when highlighted (not available from web scraper)
    "idx_within_book": 3,    # int: 1-based highlight index (used by Sheets for highlight_id)
}
```
 
## Module Responsibilities
 
### `config/__init__.py`
- Defines `BASE_DIR` (project root), `CONFIG_DIR`, `ENV_PATH`
- `load_env_file(*, override=False)`: calls `dotenv.load_dotenv` on `config/KEYS.env` and returns the path
- Safe to call multiple times; used by both `main.py` and `web/app.py`
 
### `main.py`
- `load_config()`: idempotent loader; reads env vars into module-level globals, validates required keys, resolves service account path
- `run(playwright, max_books, progress_callback, two_factor_callback, headless_login)`: performs login in a separate browser context, then scrapes highlights headless; returns list of note dicts
- GUI `__main__` block: creates `ProgressWindow`, spawns a worker thread for the pipeline, calls `window.run()` (Tkinter main loop)
- `GOOGLE_SHEETS_WORKSHEET_NAME` is no longer read; the v2 schema uses fixed sheet names
 
### `amazon/login.py`
- `perform_login(page, email, password, two_factor_callback=None, allow_manual_auth=False)`
- Navigates to `https://read.amazon.co.jp/notebook`, fills email/password, submits
- 2FA retry loop: up to `MAX_2FA_ATTEMPTS = 5`; calls `two_factor_callback(error_message=...)` to get code; re-prompts with error if Amazon rejects
- If `two_factor_callback` is `None`, falls back to the standalone `gui_utils.gui.prompt_two_factor_code()`
- If `allow_manual_auth=True` and no callback, calls `_wait_for_notebook_ready()` to poll for manual completion in the open browser
- `_wait_for_notebook_ready()` polls every 0.5s until notebook URL + selector visible, up to `NOTEBOOK_WAIT_TIMEOUT = 180000` ms
- Raises `SystemExit` for user cancellation; raises `TimeoutError` if notebook page never loads
 
### `book_transformer/transformer.py`
- Iterates `.kp-notebook-library-each-book` elements
- Clicks each book and waits 5 seconds (`time.sleep(5)`) for content to load
- Extracts title from `h3`, highlights from `#highlight`, page numbers from `#annotationHighlightHeader` via regex
- Returns a list of note dicts
 
### `notion/toNotion.py`
- `get_existing_note_keys()`: paginates through all Notion DB entries (100/page) to build a set of `(title, content, page)` tuples
- `save_notes_to_notion()`: skips notes already in Notion (dedup key = `(title, content, page)`), creates pages with `Title`, `Content`, `Page` properties
- Accepts optional `progress_callback(phase, current, total, message)` for both GUI and web progress reporting
- Uses `note_utils.build_note_key` / `build_note_key_from_note` for the dedup key
 
### `google_sheets/toSheets.py`
Implements the **v2 multi-sheet schema**. Writes to two fixed worksheets; never touches other sheets in the same spreadsheet.
- `BOOKS_SHEET = "01_books"`, `HIGHLIGHTS_SHEET = "02_highlights"`
- `_build_client()`: supports service account JSON as a file path or raw JSON string
- `_get_or_create_worksheet()`: creates the worksheet with header row if missing; repairs a missing header on an existing sheet
- `_load_books()`: returns `{book_id: row_dict}` from `01_books`
- `_load_highlight_state()`: returns `(dedup_set, max_idx_per_book)` from `02_highlights`; dedup key is `(book_id, sha1(content))`
- `save_notes_to_google_sheets()`: appends new books to `01_books`, new highlights to `02_highlights`; calls `_refresh_book_meta()` to update `highlight_count` and `last_synced_at` for touched books
- `book_id` is computed via `note_utils.stable_book_id(title)` if not already on the note dict
 
### `gui_utils/gui.py`
- All dialogs are built with Tkinter using a custom blue/gray color scheme; Font: Yu Gothic UI; Accent: `#0ea5e9`
- `ask_book_limit()`: standalone dialog, returns `int` or `None`; raises `SystemExit` on cancel
- `prompt_two_factor_code()`: standalone 2FA dialog, returns code string or `None` on cancel
- `ProgressWindow`: main-thread progress UI with per-phase progress bars (`scrape`, `notion`, `sheets`)
  - `update(phase, current, total, message)`: thread-safe via `root.after(0, ...)`
  - `prompt_two_factor_code(error_message, timeout_seconds)`: worker-thread API; spawns a `Toplevel` dialog on the main thread, blocks worker with `threading.Event`
  - `mark_done()` / `mark_error(message)`: signal pipeline completion
  - `run()`: starts the Tkinter main loop (called from GUI `__main__` block)
- `show_popup_message()`: simple informational dialog
- Private helpers use underscore prefix (`_build_window`, `_center_window`, `_build_button`, etc.)
 
### `note_utils.py`
Contains two groups of helpers:
 
**Legacy (used by `notion/toNotion.py`):**
- `normalize_text(value)`: coerce to str and strip whitespace
- `build_note_key(title, content, page)` / `build_note_key_from_note(note)`: return `(title, content, page)` tuple used as the Notion dedup key
- `has_any_note_value(values)`: True if any value is non-empty
 
**v2 (used by `google_sheets/toSheets.py` and `scripts/`):**
- `stable_book_id(title)` → `"BK-<6HEX>"` (SHA1 of title, deterministic across runs)
- `highlight_id(book_id, idx_within_book)` → `"HL-<book6>-<NNNN>"`
- `content_dedup_key(book_id, content)` → `(book_id, sha1(content))` tuple
- `today_iso()` → ISO date string
- `BOOKS_HEADERS` / `HIGHLIGHTS_HEADERS`: column order lists for the two worksheets
- `note_to_book_row()` / `note_to_highlight_row()`: shape a note dict into a row list
 
### `web/app.py`
- `create_app()`: Flask application factory; calls `load_env_file()`, registers routes, sets up Basic auth if `WEB_USERNAME`/`WEB_PASSWORD` are set
- Routes: `GET /` (index), `POST /api/start`, `POST /api/2fa`, `GET /api/events` (SSE), `GET /api/status`
- Uses a `threading.Lock` to prevent concurrent pipeline runs
- SSE stream polls `PipelineState.get_events_since()` every 0.3s and closes when status is `done` or `error`
 
### `web/pipeline.py`
- `PipelineState`: shared mutable state between Flask routes and the worker thread
  - Stores a list of SSE events (type + data dicts)
  - Status: `idle | running | waiting_2fa | done | error`
  - `request_two_factor(error_message)`: called from Playwright thread; blocks on `threading.Event` (5 min timeout)
  - `submit_two_factor(code)`: called from Flask route; unblocks the Playwright thread
  - `progress_callback(phase, current, total, message)`: drop-in replacement for `ProgressWindow.update`
- `run_pipeline(state, max_books)`: executes the full pipeline in a background thread; pushes SSE events; sets `state.status`
 
### `web_main.py`
- Creates the Flask app via `create_app()` and starts it with `app.run()`
- Reads `WEB_HOST` (default `0.0.0.0`) and `WEB_PORT` (default `5000`) from env
- Prints local + LAN access URLs on startup
 
### `scripts/migrate_legacy_sheet.py`
- One-shot migration from the legacy `Sheet1` (v1 flat schema) to `01_books` / `02_highlights`
- Usage: `python -m scripts.migrate_legacy_sheet` (dry-run) or `--apply` to write
- Reads legacy sheet column headers flexibly (case-insensitive; maps Title/Content/Page columns)
- Refuses to overwrite if destination worksheets already contain data rows
- Backfills `highlight_count` on each book row after grouping

### `scripts/split_per_book.py`
- Splits the master spreadsheet into a **fixed 50-file layout** for NotebookLM (which caps a notebook at 50 sources): `VOLUME_COUNT = 49` content *volume* files + 1 *index* file. The file count never grows, no matter how many books exist.
- Reads `01_books` + `02_highlights` from the master; the master itself is **never** modified
- Each book is pinned to a volume by `volume_for_book_id(book_id)` = `SHA1(book_id) % 49 + 1` (1-based). Deterministic and append-only: re-runs never move a book. **`VOLUME_COUNT` and this formula are permanent — changing them re-shuffles every book and forces a full NotebookLM re-import.**
- Volume sheet columns: `book_id, book_title, highlight_id, location, content`. `book_id`/`book_title` on every row make it self-describing, so a multi-book volume cannot be mis-attributed by NotebookLM.
- Index sheet columns: `book_id, title, volume, highlight_count, last_synced_at` (`volume` is the volume filename — a book→file lookup)
- Filenames are fixed (no extension): index `<prefix>_index`, volumes `<prefix>_vol_01`..`<prefix>_vol_49`. Default prefix `k2n`.
- Volumes + index are rewritten in full from the master every run (idempotent); books sorted by `book_id`, highlights by `highlight_id` for byte-stable output. Empty volumes are written header-only.
- **Does not create new spreadsheet files.** Service accounts have 0 bytes of personal Drive storage, so creating files in "My Drive" fails with `storageQuotaExceeded`. The script writes only to spreadsheets that already exist in the target folder; missing files are reported as `[missing]`. Because the 50 filenames are fixed, the user creates the 50 empty Sheets **once** — new books afterwards need no new files.
- Default subfolder is `notebooklm/` (was `per_book/`). Legacy `per_book/` one-file-per-book Sheets are **never** auto-deleted; the user retires them manually.
- CLI flags:
  - `--apply`: actually write (default is dry-run)
  - `--folder <name>`: destination subfolder name (default: `notebooklm`)
  - `--prefix <str>`: filename prefix for volume/index files (default: `k2n`)
  - `--parent-folder <FOLDER_ID>`: explicit Drive folder ID to host the destination subfolder. Required when the master spreadsheet lives in "My Drive" root (Drive API cannot resolve its parent for service-account-shared files at the root). Validated up-front via `_validate_parent_folder()`: must be an accessible folder with `canAddChildren=true`
- Pure helpers (`safe_title_for_filename`, `volume_for_book_id`, `volume_filename`, `index_filename`, `all_target_filenames`, `group_books_by_volume`, `volume_rows`, `index_rows`, `group_highlights_by_book`) are covered by `test/test_split_per_book.py`; runtime deps (`gspread`, `google-auth`) are guarded so tests can import the module without them
 
## Code Conventions
 
### Naming
- Constants: `UPPER_SNAKE_CASE` (e.g., `LOAD_TIMEOUT`, `EMAIL_SELECTOR`)
- Functions: `snake_case` (e.g., `perform_login`, `extract_notes`)
- Private helpers: `_snake_case` (e.g., `_build_client`, `_get_existing_contents`)
- Classes: `PascalCase`
 
### Imports (standard ordering)
```python
# 1. Standard library
import os, re, time
from pathlib import Path
 
# 2. Third-party
from playwright.sync_api import sync_playwright
from notion_client import Client
from tqdm import tqdm
 
# 3. Local modules
import amazon.login
from book_transformer import transformer
from gui_utils.gui import ask_book_limit
```
 
### Error Handling
- Validate environment variables at startup; raise `ValueError` with a clear message
- Use try/except around Playwright timeout checks (2FA presence is optional)
- Wrap individual Notion/Sheets write calls in try/except and print errors, but continue processing remaining notes
- Raise `Exception` (not `SystemExit`) for unrecoverable login failures
- Use `SystemExit` only for user-initiated cancellations (e.g., closing 2FA dialog)
 
### Deduplication
- **Notion**: dedup key is `(title, content, page)` tuple; existing keys fetched into a set before writing
- **Sheets v2**: dedup key is `(book_id, sha1(content))`; book_id is deterministic from the title
- Both fetch existing state upfront, then skip already-present entries
 
### Async
- `nest_asyncio.apply()` is called at the top of `main.py` to allow async event loops in sync contexts
- The app uses Playwright's sync API throughout; no `async def` functions
 
## Notion Database Schema
 
The Notion database must have these properties:
| Property | Type       | Notes                        |
|----------|------------|------------------------------|
| Title    | title      | Book title                   |
| Content  | rich_text  | Highlight text (dedup key)   |
| Page     | rich_text  | Page number string           |
 
## Google Sheets Schema (v2)
 
Two worksheets are managed by `google_sheets/toSheets.py`. Other sheets (`03_book_summary`, `04_highlight_tags`, `05_tags_taxonomy`) are never touched by this tool.
 
**`01_books`** — one row per book:
| book_id | title | title_normalized | author | genre | reading_status | finished_at | rating | amazon_asin | cover_url | notion_url | highlight_count | first_synced_at | last_synced_at |
|---------|-------|-----------------|--------|-------|---------------|-------------|--------|------------|-----------|-----------|----------------|----------------|---------------|
 
**`02_highlights`** — one row per highlight:
| highlight_id | book_id | book_title | content | location | page | highlighted_at | synced_at | source |
|-------------|---------|-----------|---------|----------|------|---------------|-----------|--------|
 
Primary keys:
- `book_id` = `BK-` + SHA1(title)[0:6] (uppercase). Stable as long as the title string does not change.
- `highlight_id` = `HL-<book6>-<NNNN>` (NNNN is 1-based per-book index, zero-padded to 4 digits).
- Dedup key on `02_highlights`: `(book_id, sha1(content))`.
 
Both worksheets and their header rows are created automatically if missing.
 
Invariants:
1. `kindle2notion` writes only to `01_books` and `02_highlights`.
2. AI-populated sheets (`03`–`05`) are never read or modified.
3. Existing `book_id` / `highlight_id` values are never changed after initial write.
 
To migrate from a legacy `Sheet1` to v2, run `scripts/migrate_legacy_sheet.py`.
 
## Render Deployment (Docker)
 
The Flask web UI can be deployed to Render as a Docker web service. Files:
- `Dockerfile` — Python 3.12 + Playwright Chromium image; `CMD ["python", "web_main.py"]`
- `.dockerignore` — keeps secrets/caches/local data out of the build context
- `render.yaml` — Render Blueprint: one web service, `healthCheckPath: /healthz`, secrets as `sync: false`
- `deploy/render/README.md` — full step-by-step deployment guide
 
Render-specific behaviour built into the code:
- `web_main.py` binds `PORT` (Render-injected) first, then `WEB_PORT`, then `5000`
- `main.py` reads the `STORAGE_STATE_PATH` env var so the Amazon session can live on a mounted disk; the default is unchanged
- `main.py` launches Chromium with `--no-sandbox --disable-dev-shm-usage` (`BROWSER_LAUNCH_ARGS`), required to run headless as root in a container
- `web/app.py` exposes `GET /healthz` (unauthenticated, exempt from Basic auth) for Render health checks
- Config still comes from env vars: `load_env_file()` is a no-op when `config/KEYS.env` is absent, so Render dashboard env vars are read directly
 
The free plan has no persistent disk, so `storage_state.json` is lost on every cold start (2FA re-login each time). See `deploy/render/README.md` for the paid-plan disk setup. The VPS path (`deploy/README.md`) is unaffected and still valid.
 
## Key Files to Ignore
 
The following are git-ignored and must not be committed:
- `config/KEYS.env` — credentials
- `storage_state.json` — browser session (auto-generated)
- `__pycache__/`, `*.pyc` — Python cache
- `CODEX_KEY_CONTEXT.md` — Claude session context
 
## Testing Notes
 
- `test/test_amazon/test_login.py`: tests for `amazon/login.py`; uses a `FakePage` mock class and `monkeypatch.setattr` to inject responses
- `test/test_note_utils.py`: pure-function tests for `note_utils.py` (legacy helpers + v2 ID/row builders); no network access needed
- `test/test_split_per_book.py`: pure-function tests for `scripts/split_per_book.py` (filename sanitisation, grouping, row shaping); no network access needed
- The test directory is git-ignored; no CI pipeline exists
- When modifying `amazon/login.py`, update `test/test_amazon/test_login.py`
- When modifying `note_utils.py`, update `test/test_note_utils.py`
- When modifying the pure helpers in `scripts/split_per_book.py`, update `test/test_split_per_book.py`
 
## Common Gotchas
 
- The Amazon notebook URL targets Japan (`read.amazon.co.jp`). Do not change to `.com`.
- `time.sleep(5)` between book clicks is intentional — the page loads highlights dynamically.
- If `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` starts with `{`, it is treated as a raw JSON string, not a file path.
- `storage_state.json` is reused on the next run if it already exists (no explicit expiry logic).
- The GUI requires a display server (X11/Wayland). Running headlessly in CI will fail unless a virtual display is provided.
- Service accounts have **0 bytes of personal Drive storage**. They can edit files shared with them and create folders (0 bytes), but they cannot own new files in "My Drive" — Google rejects creation with `storageQuotaExceeded`. Workarounds: (a) Workspace Shared Drive, (b) OAuth user credentials, (c) pre-create files manually. `scripts/split_per_book.py` uses option (c).
- For files in "My Drive" root that are shared with the service account (not owned), the Drive API may return an empty `parents` field. `scripts/split_per_book.py` handles this via the `--parent-folder` CLI flag.