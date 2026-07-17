# CLAUDE.md
 
This file provides guidance for AI assistants working on the kindle2notion codebase.
Must to be update this .md after every edits.
 
## Project Overview
 
kindle2notion is a Python automation tool that scrapes Kindle highlights from the Amazon Kindle notebook page (Japan: `read.amazon.co.jp/notebook`) and exports them to a Notion database. Optionally, highlights are also synced to Google Sheets.

**Google Sheets data model (current).** The single source of truth on the Sheets side is the **NotebookLM 100-file layout** managed by `scripts/split_per_book.py` (99 volume files + 1 index, in a `notebooklm/` Drive folder). After a scrape (and after a manual-highlight add) notes flow **directly** into those 100 files via `split_per_book.sync_notes_to_notebooklm`. The earlier "master" spreadsheet with the `01_books` / `02_highlights` worksheets is **retired** — nothing writes it anymore. `google_sheets/toSheets.py` and `scripts/migrate_legacy_sheet.py` are kept only as deprecated legacy/reference code.
 
The application uses Playwright for browser automation, the official Notion Python SDK, and a Tkinter-based GUI for user interaction (book limit selection, 2FA code entry).
 
## Repository Structure
 
```
kindle2notion/
├── main.py                         # Application entry point and orchestrator (GUI mode)
├── web_main.py                     # Entry point for Flask web server
├── note_utils.py                   # Shared helpers: legacy dedup keys + note_key_hash + v2 ID/row builders
├── run_history.py                  # Best-effort run history recording (shared by GUI + web)
├── gunicorn.conf.py                # Production server config (Docker/Render; 1 gthread worker)
├── __init__.py                     # Package marker
├── amazon/
│   ├── __init__.py
│   └── login.py                    # Amazon authentication via Playwright (selector races, is_session_valid)
├── book_transformer/
│   ├── __init__.py
│   └── transformer.py              # Highlight extraction: XHR mode (default) + DOM fallback
├── config/
│   ├── __init__.py                 # BASE_DIR, CONFIG_DIR, load_env_file()
│   └── KEYS.env                    # Credentials file (git-ignored, must be created manually)
├── frontend/                       # The web UI (one codebase: served by Flask AND deployed to Vercel)
│   ├── index.html
│   └── static/
│       ├── app.js                  # apiFetch/fetchSSE, 接続設定 panel, manual-entry flows
│       └── style.css
├── google_sheets/
│   ├── __init__.py
│   └── toSheets.py                 # DEPRECATED: legacy writer for the retired 01_books/02_highlights master
├── gui_utils/
│   ├── __init__.py
│   └── gui.py                      # Tkinter GUI dialogs + ProgressWindow
├── notion/
│   ├── __init__.py
│   ├── dedup_cache.py              # Notion dedup key cache (seed / load / append / dirty-reseed)
│   └── toNotion.py                 # Notion database export module
├── scripts/
│   ├── __init__.py
│   ├── add_manual_highlights.py    # Add non-Kindle / physical book highlights to Notion + NotebookLM files
│   ├── migrate_legacy_sheet.py     # DEPRECATED one-shot: legacy Sheet1 -> retired v2 master
│   ├── resync_notion_cache.py      # Rebuild the Notion dedup cache from the live database
│   └── split_per_book.py           # NotebookLM 100-file layout: source-of-truth sync + index/volume helpers
├── storage/                        # Operational store (Turso in prod, local SQLite fallback)
│   ├── __init__.py                 # get_store()/get_store_or_none() factory + schema bootstrap
│   ├── base.py                     # AppStore ops (session/dedup/runs) + DDL
│   ├── local.py                    # stdlib sqlite3 backend (connection per call)
│   ├── session_store.py            # storage_state.json <-> store mirroring (newer-wins hydrate)
│   └── turso.py                    # Turso libsql HTTP v2 pipeline backend (requests, no native deps)
├── web/
│   ├── __init__.py
│   ├── app.py                      # Flask application factory (routes, SSE, Basic auth, frontend serving)
│   ├── cors.py                     # Allowlist CORS for the cross-origin (Vercel) frontend
│   └── pipeline.py                 # PipelineState + run_pipeline for the web worker thread
├── requirements/
│   └── requirements.txt            # Python package dependencies
└── test/                           # git-ignored, local-only
    ├── compare_scrape_modes.py     # manual xhr-vs-dom diff against the real account (not collected)
    ├── test_note_utils.py          # pytest tests for note_utils (legacy + v2 helpers)
    ├── test_storage.py             # AppStore + SQLite/Turso backends
    ├── test_session_store.py       # session hydrate/persist
    ├── test_main_run.py            # main.run() control flow (fast path / web / GUI)
    ├── test_transformer.py         # XHR mode, pagination, fallback, DOM waits
    ├── test_to_notion.py           # dedup cache integration
    ├── test_web_app.py             # routes, CORS, SSE pings, run history recording
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
 
# Optional — Drive folder for the NotebookLM 100-file set. Set it to EITHER the
# folder that holds the 100 files directly, OR a parent that contains a notebooklm/
# subfolder (the code tries the subfolder first, then falls back to the folder
# itself). This is the primary anchor now that the 01_books/02_highlights master
# is retired; set it so the sync can locate the files without --parent-folder.
NOTEBOOKLM_PARENT_FOLDER_ID=
 
# Optional — Basic auth for the web UI (omit to disable auth)
WEB_USERNAME=
WEB_PASSWORD=
 
# Optional — web server bind address/port (defaults: 0.0.0.0 / 5000)
WEB_HOST=127.0.0.1
WEB_PORT=5000

# Optional — Turso operational store (session persistence + Notion dedup
# cache + run history). Unset -> local SQLite fallback (local_store.db),
# and the Amazon session stays file-only like before.
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=
```

Tuning env vars (all optional): `SCRAPE_MODE` (`xhr` default | `dom` forces the
legacy click walk), `NOTION_DEDUP_MODE` (`cache` default | `scan` restores the
per-run full Notion scan), `K2N_LOCAL_DB_PATH` (SQLite fallback path),
`CORS_ALLOWED_ORIGINS` (comma-separated exact origins for the Vercel frontend;
unset = no CORS headers), `GUNICORN_THREADS` (prod server threads, default 8).
 
`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` can be either a file path or a raw JSON string starting with `{`.
`GOOGLE_SHEETS_SPREADSHEET_ID` is no longer used as a data store (the `01_books`/`02_highlights` master is retired); it is kept only as a fallback anchor for resolving the `notebooklm/` Drive folder. Set `NOTEBOOKLM_PARENT_FOLDER_ID` as the primary way to locate that folder. `GOOGLE_SHEETS_ENABLED` still requires both `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` and `GOOGLE_SHEETS_SPREADSHEET_ID` to be set (it gates the whole Sheets path).
 
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
2. **Fast path**: the saved session (`storage_state.json`, hydrated from Turso when
   configured) is validated headlessly; if it still reaches the notebook, scraping
   starts immediately — no login, no 2FA, no visible browser
3. Only when the session is missing/stale: Amazon login (GUI = visible browser
   with 2FA dialog / manual auth; web = headless with 2FA relayed over SSE),
   then the session is saved to `storage_state.json` and mirrored to Turso
4. Highlights are scraped (XHR mode by default; DOM click-walk as fallback)
5. Saves to Notion (dedup via the cached key set) and syncs into the NotebookLM
   100-file layout (if Google Sheets is configured; the 01_books/02_highlights
   master is retired)
 
## Running Tests
 
```bash
py -3 -m pytest test/ --basetemp=.pytest_tmp
```
 
Tests use pytest with monkeypatching. There is no separate test runner script. The test directory is git-ignored, so tests exist only locally. On this Windows machine the `--basetemp` flag is required (the default temp dir is permission-denied). Some tests in `test_split_per_book.py` / `test_add_manual_highlights.py` are skip-guarded because they target an incremental-NotebookLM-merge API that only exists on an unmerged branch (commit `f056383`).
 
## Application Flow
 
**`main.run()` (shared by both entry points):**
```
run(playwright, max_books, progress_callback, two_factor_callback, headless_login)
  └── load_config(); store = get_store_or_none()
  └── hydrate_session_file(store, STORAGE_STATE_PATH)   # Turso -> file, newer-wins
  └── headless browser + saved storage_state
        ├── is_session_valid()  ── True ──▶ extract_notes() -> persist session -> return
        └── False/missing:
              ├── headless_login=True (web): perform_login() in a fresh context of the
              │     SAME browser -> persist session -> extract_notes() in that context
              └── headless_login=False (GUI): visible login browser (2FA dialog /
                    manual auth) -> persist session -> fresh headless browser scrapes
```
 
**GUI mode (`python main.py`):**
```
main.py __main__
  └── load_config()                 # Load/validate KEYS.env once
  └── prompt_book_limit()           # Tkinter: ask how many books to process
  └── ProgressWindow.run()          # Tkinter main loop (blocks until done/error)
        worker thread:
          └── record_run_start("gui")
          └── run(playwright, ...)             # see shared flow above
          └── toNotion.save_notes_to_notion()
          └── split_per_book.sync_notes_to_notebooklm()  # Only if GOOGLE_SHEETS_ENABLED
          └── record_run_end(...)
```
 
**Web mode (`python web_main.py` locally; gunicorn in Docker/Render):**
```
web_main.py
  └── create_app()                  # Flask factory: load config, register routes, init_cors
        /api/start  POST            # Body: {max_books?, full_resync?}; spawns worker thread
          worker thread:
            └── run_pipeline(state, max_books, full_resync)
                  └── record_run_start("web")
                  └── main.run()   # headless_login=True
                  └── toNotion.save_notes_to_notion(force_resync=full_resync)
                  └── split_per_book.sync_notes_to_notebooklm()  # Only if GOOGLE_SHEETS_ENABLED
                  └── record_run_end(...)
        /api/2fa    POST            # Unblocks the waiting Playwright thread
        /api/events GET (SSE)       # Streams progress; ': ping' comment every 15s
        /api/runs   GET             # Last 20 runs from the operational store
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
    "location": "...",       # str: Kindle location string (preferred over page in the volume "location" column)
    "highlighted_at": "",    # str: ISO date when highlighted (not available from web scraper)
    "idx_within_book": 3,    # int: 1-based highlight index (honored when numbering highlight_id)
}
```
 
## Module Responsibilities
 
### `config/__init__.py`
- Defines `BASE_DIR` (project root), `CONFIG_DIR`, `ENV_PATH`
- `load_env_file(*, override=False)`: calls `dotenv.load_dotenv` on `config/KEYS.env` and returns the path
- Safe to call multiple times; used by both `main.py` and `web/app.py`
 
### `main.py`
- `load_config()`: idempotent loader; reads env vars into module-level globals, validates required keys, resolves service account path
- `run(playwright, max_books, progress_callback, two_factor_callback, headless_login)`: session-validation-first (see Application Flow). Fast path = one headless browser, no login. Web login shares that browser; GUI login opens a visible browser. Persists the session (file + Turso) after login and after each scrape
- GUI `__main__` block: creates `ProgressWindow`, spawns a worker thread for the pipeline (with run-history recording), calls `window.run()` (Tkinter main loop). When `GOOGLE_SHEETS_ENABLED`, the worker calls `split_per_book.sync_notes_to_notebooklm(notes, ...)` (NOT the retired `toSheets.save_notes_to_google_sheets`) to sync into the NotebookLM 100-file layout
- `GOOGLE_SHEETS_WORKSHEET_NAME` is no longer read; the v2 schema uses fixed sheet names
 
### `amazon/login.py`
- `perform_login(page, email, password, two_factor_callback=None, allow_manual_auth=False)`
- Navigates to `https://read.amazon.co.jp/notebook`, fills email/password, submits
- Instead of blind fixed-timeout waits, `_wait_for_first_visible()` races the possible
  next states (`[password, 2FA, notebook]`): an already-authenticated or no-2FA login
  proceeds the moment its next state renders (the old code burned up to 15s+15s)
- `is_session_valid(page)`: probe used by `main.run()`'s fast path — goto notebook and
  race `[notebook, email, password]`; only a visible library counts as valid
- 2FA retry loop: up to `MAX_2FA_ATTEMPTS = 5`; calls `two_factor_callback(error_message=...)`;
  acceptance is detected by `_wait_until_hidden()` on the OTP input
- If `two_factor_callback` is `None`, falls back to the standalone `gui_utils.gui.prompt_two_factor_code()`
- If `allow_manual_auth=True` and no callback, calls `_wait_for_notebook_ready()` to poll for manual completion in the open browser
- `_wait_for_notebook_ready()` polls every 0.5s until notebook URL + selector visible, up to `NOTEBOOK_WAIT_TIMEOUT = 180000` ms
- Raises `SystemExit` for user cancellation; raises `TimeoutError` if notebook page never loads
- All helpers use only `query_selector` / `is_visible` / `wait_for_timeout` / `url` — the exact surface `test_login.py`'s FakePage implements
 
### `book_transformer/transformer.py`
Two scrape modes behind the unchanged `extract_notes(page, max_books, progress_callback)`;
both emit notes through the shared `_extract_current_book()` so the dicts are identical.
- **XHR mode (default)**: enumerate sidebar ASINs (`.kp-notebook-library-each-book` id attr),
  `page.request.get()` each book's annotation fragment (`/notebook?asin=...&contentLimitState=...`),
  render it with `page.set_content()` and reuse the DOM selectors; follows the hidden
  pagination inputs (`.kp-notebook-annotations-next-page-start` / `.kp-notebook-content-limit-state`)
  so large books are complete (DOM mode only sees the initially rendered chunk)
- **DOM mode**: legacy click walk, now waiting on the clicked ASIN's XHR response
  (`page.expect_response`, 10s) + 200ms settle instead of the old fixed 1.5s pause
  (the fixed pause remains as the per-click safety net)
- Any XHR-mode failure (missing ASIN, non-200, missing `h3`, runaway pagination) prints a
  warning and reruns the whole scrape in DOM mode; `SCRAPE_MODE=dom` forces DOM outright
- `last_scrape_mode` records what actually ran (`xhr` / `dom` / `dom-fallback`) for run history
- Extracts title from `h3`, highlights from `#highlight`, page numbers from `#annotationHighlightHeader` via regex
 
### `notion/toNotion.py` + `notion/dedup_cache.py`
- `save_notes_to_notion(..., force_resync=False)`: dedup keys come from the operational
  store's cache when available (`dedup_cache.load_dedup_hashes` — one query), falling back
  to the legacy full scan when the store/cache is off. Creates pages with `Title`, `Content`, `Page`
- The cache is seeded once via `fetch_existing_note_keys_strict()` (raises on API errors so a
  partial fetch can never poison the cache); `get_existing_note_keys()` stays the lenient
  variant (returns what it could collect). Hashes (`note_utils.note_key_hash`) are stored,
  not raw text; new-page hashes are appended in flushed batches (`DEDUP_FLUSH_EVERY = 100`)
- Any cache-append failure marks the cache dirty -> next load reseeds from Notion. Failure
  direction is always "extra full scan", never "duplicate page"
- **Documented behavior change**: pages deleted by hand in Notion stay deleted on later syncs.
  `scripts/resync_notion_cache.py` or `/api/start {"full_resync": true}` rebuilds the cache
  (old semantics on demand). `NOTION_DEDUP_MODE=scan` disables caching entirely
- Accepts optional `progress_callback(phase, current, total, message)` for both GUI and web progress reporting
- Uses `note_utils.build_note_key` / `build_note_key_from_note` for the dedup key
 
### `storage/` (operational store)
- `get_store()` / `get_store_or_none()`: Turso when `TURSO_DATABASE_URL`+`TURSO_AUTH_TOKEN`
  are set, else local SQLite at `K2N_LOCAL_DB_PATH` (default `local_store.db`). Schema
  (`app_session`, `notion_dedup_key`, `notion_dedup_meta`, `run_history`) is created on first use
- `turso.py` speaks the libsql **HTTP v2 pipeline** with plain `requests` (no native wheels —
  works on the Windows dev box); batched INSERTs, 10s timeout, 2 retries on 5xx/connection errors
- `local.py` opens a connection per call (Flask threads + worker thread safe)
- `session_store.py`: `hydrate_session_file()` (store -> file, newer-wins by timestamp) and
  `persist_session_file()` (file + store). Local mode is file-only (`supports_session=False`)
- Everything is best-effort by contract: callers wrap store usage and degrade (session -> file,
  dedup -> full scan, history -> skip). A broken store must never fail a sync run
 
### `run_history.py`
- `record_run_start(mode)` / `record_run_end(store, run_id, **fields)` / `run_stats(notes, ...)` —
  shared by the GUI worker and `web/pipeline.py`; lives at top level to avoid import cycles
 
### `google_sheets/toSheets.py` — DEPRECATED (retired master)
**No production path calls this anymore.** It writes the retired `01_books` / `02_highlights` master; the live source of truth is the NotebookLM 100-file layout (`scripts/split_per_book.py`). Kept only as: (a) the reference dedup + `highlight_id` numbering implementation that `merge_notes_into_volume` mirrors, (b) the engine behind `split_per_book --from-master` (legacy backfill), and (c) `migrate_legacy_sheet.py`. `SCOPES` is still imported by `split_per_book`. Do not wire `save_notes_to_google_sheets` / `list_existing_books` into new code.
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
 
**v2 (live consumers: `scripts/split_per_book.py` and `scripts/add_manual_highlights.py`; also still imported by the deprecated `google_sheets/toSheets.py`):**
- `stable_book_id(title)` → `"BK-<6HEX>"` (SHA1 of title, deterministic across runs)
- `highlight_id(book_id, idx_within_book)` → `"HL-<book6>-<NNNN>"`
- `content_dedup_key(book_id, content)` → `(book_id, sha1(content))` tuple
- `today_iso()` → ISO date string
- `BOOKS_HEADERS` / `HIGHLIGHTS_HEADERS`: column order lists for the two worksheets
- `note_to_book_row()` / `note_to_highlight_row()`: shape a note dict into a row list
 
### `web/app.py`
- `create_app()`: Flask application factory; calls `load_env_file()`, registers routes, sets up Basic auth if `WEB_USERNAME`/`WEB_PASSWORD` are set, serves the UI from `frontend/` (`send_from_directory`; static folder = `frontend/static`), and calls `web.cors.init_cors(app)`
- Routes: `GET /` (index), `POST /api/start` (body: `max_books?`, `full_resync?`), `POST /api/2fa`, `GET /api/events` (SSE), `GET /api/status`, `GET /api/runs` (last 20 runs)
- Basic auth **skips `OPTIONS`** (CORS preflights never carry Authorization); `web/cors.py` answers allowlisted preflights (`CORS_ALLOWED_ORIGINS`, exact-match, unset = no CORS at all)
- **Manual highlights API** (phone / assistant friendly; mirrors `scripts/add_manual_highlights.py` so the *same* flow works from a phone against the deployed service):
  - `GET /api/manual/books` — read-only fuzzy title match ("この本ですか？"). Query: `title` (rank against existing books; omit to list all), `cutoff` (0..1), `full=1` (also include the whole book list). Reuses `build_books_result()`. Returns `sheets_configured: false` (HTTP 200) when Sheets is off so the caller can fall back.
  - `POST /api/manual/highlights` — add highlights. Body = the CLI JSON payload (`{title, highlights}` or `{books:[...]}`) plus control keys `apply` (default `false` = dry-run), `notion_only`/`sheets_only`. Reuses `build_notes_from_payload()` + `write_notes()`. Always HTTP 200 with an `ok` flag + `problems` list — a partial write failure is `ok: false`, **not** an HTTP error, so callers must check `ok`. Bad payload → 400.
  - These endpoints are independent of the Kindle pipeline, so they do **not** take `run_lock`; both writers are dedup-safe. They are covered by Basic auth like every other route. Tested in `test/test_web_manual.py` (Flask test client; network helpers monkeypatched, the `apply=false` dry-run path tested for real).
- Uses a `threading.Lock` to prevent concurrent pipeline runs
- SSE stream polls `PipelineState.get_events_since()` every 0.3s, emits a `: ping` comment after 15 quiet seconds (`SSE_PING_INTERVAL_SECONDS` — keeps proxies from idle-closing during the 2FA wait), and closes when status is `done` or `error`. Every new connection replays from index 0, so client reconnects are lossless
 
### `web/pipeline.py`
- `PipelineState`: shared mutable state between Flask routes and the worker thread
  - Stores a list of SSE events (type + data dicts)
  - Status: `idle | running | waiting_2fa | done | error`
  - `request_two_factor(error_message)`: called from Playwright thread; blocks on `threading.Event` (5 min timeout)
  - `submit_two_factor(code)`: called from Flask route; unblocks the Playwright thread
  - `progress_callback(phase, current, total, message)`: drop-in replacement for `ProgressWindow.update`
- `run_pipeline(state, max_books, full_resync=False)`: executes the full pipeline in a background thread; pushes SSE events; sets `state.status`; records run history via `run_history.py`; passes `force_resync` to the Notion writer. When `GOOGLE_SHEETS_ENABLED`, it calls `split_per_book.sync_notes_to_notebooklm(notes, ...)` (NOT the retired `toSheets` writer)
 
### `web_main.py`
- Creates the Flask app via `create_app()`; `python web_main.py` runs the dev server (local / VPS), while Docker/Render runs `gunicorn -c gunicorn.conf.py web_main:app`
- Reads `WEB_HOST` (default `0.0.0.0`) and `WEB_PORT` (default `5000`) from env
- Prints local + LAN access URLs on startup
 
### `frontend/static/app.js`
- `apiFetch(path, opts)`: prefixes the saved backend URL and adds a Basic `Authorization` header when the 接続設定 panel is configured (localStorage keys `k2n_api_base` / `k2n_api_user` / `k2n_api_pass`); same-origin use sends no explicit header (browser-native Basic auth, unchanged)
- SSE is read via **fetch + ReadableStream** (`connectSSE`/`openEventStream`/`handleSSEFrame`) — EventSource cannot send Authorization headers. Abnormal stream end retries after 2s; the server's replay-from-zero makes that lossless
- Start screen extras: `full_resync` checkbox (one-shot, auto-unchecks), backend wake-up banner polling `/healthz` every 5s while a sleeping Render instance spins up
 
### `scripts/migrate_legacy_sheet.py` — DEPRECATED
- One-shot migration from the legacy `Sheet1` (v1 flat schema) to `01_books` / `02_highlights`. **The destination master is now retired** (superseded by `split_per_book.sync_notes_to_notebooklm`); this script is kept for historical reference only and should not be run on live data.
- Usage: `python -m scripts.migrate_legacy_sheet` (dry-run) or `--apply` to write
- Refuses to overwrite if destination worksheets already contain data rows

### `scripts/split_per_book.py`
**Owns the NotebookLM 100-file layout, which is the single source of truth for highlights.** `VOLUME_COUNT = 99` content *volume* files + 1 *index* file (100 total, in a `notebooklm/` Drive folder). The file count never grows. (Expanded from 49+1=50 in 2026-07 when NotebookLM raised its source cap to 100; the one-time `--redistribute` migration re-shuffled every book into the new layout.) Each volume file is **self-describing** (every row carries `book_id` + `book_title`), so a volume's full state is recoverable from the volume itself.

**Primary path — `sync_notes_to_notebooklm(notes, *, apply=True, progress_callback=None, ...)`** (called automatically after a Kindle scrape from `main.py` / `web/pipeline.py`, and from `add_manual_highlights.write_notes`):
- Groups incoming notes by their volume (`stable_book_id(title)` → `volume_for_book_id`); pre-counts blank-title/content notes as `skipped_invalid`.
- Reads back **only the affected volume files** (a normal scrape touches a few), reconstructs each via `_volume_row_to_highlight`, then `merge_notes_into_volume(...)` dedups by `content_dedup_key=(book_id, sha1(content))` and assigns `highlight_id` continuing from the volume's max (honoring `idx_within_book`). Untouched books in an affected volume are re-serialized verbatim.
- Rewrites the touched volumes + refreshes the index **only for touched books** (reads the existing index, overlays the changed books' `volume`/`highlight_count`/`last_synced_at`, preserves every untouched row — so untouched books keep their stored count + date).
- Files absent from the folder go into `missing_files` (service accounts cannot create Drive files) and their highlights are NOT written. Empty `notes` short-circuits with zero I/O. Returns `{new_books, new_highlights, skipped_duplicates, skipped_invalid, total_notes, missing_files, touched_volumes}`. Progress uses the existing `"sheets"` phase, one tick per file.
- **`list_books_from_index(service_account_file, spreadsheet_id=None, *, parent_folder_id=None)`** — read-only catalogue from the index file (`[{book_id, title, author:"", highlight_count}]`, `author` always `""` since the index has no author column). Replaces `toSheets.list_existing_books` for the manual-add title-matching guard. Returns `[]` if the index is missing.
- Each book is pinned to a volume by `volume_for_book_id(book_id)` = `SHA1(book_id) % 99 + 1` (1-based). Deterministic and append-only. **`VOLUME_COUNT` and this formula are load-bearing — changing them re-shuffles every book, requires the one-time `--redistribute` migration, and forces a full NotebookLM re-import.**
- Volume columns: `book_id, book_title, highlight_id, location, content`. Index columns: `book_id, title, volume, highlight_count, last_synced_at`. There is **no `source`, `author`, or metadata column** anywhere in the 100 files — manual-book metadata (BOOK_META_KEYS) and the `source` label are written to Notion but NOT to the Sheets side.
- Filenames are fixed (no extension): index `<prefix>_index`, volumes `<prefix>_vol_01`..`<prefix>_vol_99`. Default prefix `k2n`. Output is byte-stable (books sorted by `book_id`, highlights by `highlight_id`).
- **Write throttling**: each rewrite is `clear()` + `update()` = 2 write requests. `_write_volume()` paces each write (`WRITE_THROTTLE_SECONDS`) and retries on a 429 (`QUOTA_RETRY_WAIT_SECONDS` × `MAX_QUOTA_RETRIES`). An incremental sync touches only a few files; a large first sync warns when >20 volumes are affected.
- **Does not create new spreadsheet files.** The user creates the 100 empty Sheets **once**; missing files are reported, never created.
- **CLI** (now secondary): `python -m scripts.split_per_book [--apply]` rebuilds **only the index** from the 99 volumes (safe; never reads the master, never overwrites a volume — useful for index recovery). `--from-master` is the **LEGACY** path: it reads the retired `01_books`/`02_highlights` and OVERWRITES all 100 files — it will clobber any highlights added after the master was last updated, so it prints a loud warning and is only for a one-time backfill. `--redistribute` is the **one-time migration** after a `VOLUME_COUNT` change: it harvests every existing volume file (all reads throttled, before any write), re-buckets every book with the current formula, and rewrites all 100 files + index; it aborts up front unless every target file already exists, and on `--apply` dumps a local JSON backup (`backups/redistribute-<ts>.json`, git-ignored) first — an interrupted apply is resumed with `--from-backup <file> --apply` (skips re-harvesting the partially rewritten volumes). `--redistribute` and `--from-master` are mutually exclusive. Other flags: `--folder` (default `notebooklm`), `--prefix` (default `k2n`), `--parent-folder <FOLDER_ID>`.
- **Folder resolution order**: `--parent-folder` flag / `parent_folder_id` arg → `NOTEBOOKLM_PARENT_FOLDER_ID` env var → the master spreadsheet's own Drive parent (fallback only). Because the master is retired/trashed, set `NOTEBOOKLM_PARENT_FOLDER_ID` in `config/KEYS.env` as the primary anchor. The configured folder may be **either** the parent of a `notebooklm/` subfolder **or** the folder that holds the 100 files directly: `_resolve_notebooklm_folder` looks for the named subfolder first and, if absent, uses the configured folder itself (so pointing the env var straight at the 100-file folder works).
- Pure helpers (`safe_title_for_filename`, `volume_for_book_id`, `volume_filename`, `index_filename`, `all_target_filenames`, `group_books_by_volume`, `volume_rows`, `index_rows`, `group_highlights_by_book`, `_volume_row_to_highlight`, `_index_row_to_book`, `volumes_for_book_ids`, `merge_notes_into_volume`, `merge_summaries`, `plan_redistribution`) and the orchestrator (`sync_notes_to_notebooklm` / `list_books_from_index`, with Drive faked in-memory) are covered by `test/test_split_per_book.py`. `note_utils` is imported unconditionally (pure stdlib); `gspread`/`google-auth` are guarded behind `_RUNTIME_DEPS_OK` so tests import the module without them. ⚠️ The local-only tests were written against `VOLUME_COUNT = 49`; any assertion hardcoding a book's volume number, a `vol_NN` filename, or a layout size of 49/50 must be updated for the 99+1 layout (the 2026-07 expansion could not touch `test/` because it is git-ignored and absent from the cloud checkout).
 
### `scripts/add_manual_highlights.py`
- Companion path to the Kindle scraper for **non-Kindle / physical books** (paper books, PDFs, library loans, other-store e-books). Highlights are supplied by hand (typically by an AI assistant such as Claude Code) instead of being scraped.
- Reuses the same writers as the Kindle scrape: `toNotion.save_notes_to_notion()` (always) + `split_per_book.sync_notes_to_notebooklm()` (if Google Sheets is configured). Output is identical to scraped highlights. NOTE: the `source` label and book metadata (author/genre/…) are accepted on the payload but are **no longer persisted anywhere** — Notion stores only Title/Content/Page, and the 100-file layout has no metadata/`source` columns (they only ever lived on the retired `01_books`/`02_highlights`).
- Input: `--input <file.json>`, `--stdin`, or quick mode `--title` + repeated `--highlight`. JSON payload accepts a `books` array, a single-book shorthand (`{title, highlights}`), or a bare list of books; each highlight may be an object (`content` + optional `page`/`location`/`highlighted_at`/`source`) or a bare string.
- Optional book metadata (`author`, `genre`, `reading_status`, `finished_at`, `rating`, `amazon_asin`, `cover_url`, `notion_url`) is still accepted on the payload but is **no longer persisted anywhere** (Notion stores only Title/Content/Page; the retired `01_books` was its only home; the NotebookLM index/volumes have no metadata columns). A manual book merges with an existing book only when the title matches exactly (`book_id` = `stable_book_id(title)`).
- Dry-run by default (prints a `[plan]`); `--apply` writes. `--notion-only` / `--sheets-only` target one destination. Dedup is handled by the writers, so re-runs are safe. On `--apply`, the CLI surfaces `failed` (Notion) and `skipped_invalid` (Sheets dropped rows), prints a `[partial failure] ...` line, and exits non-zero if either is > 0. Input files are read as `utf-8-sig` (tolerates a BOM from Windows editors / PowerShell `Out-File`). Input sources are mutually exclusive (0 or >1 → argparse error, exit 2); bad file / malformed JSON / TTY `--stdin` raise a clean `SystemExit` instead of a traceback or hang.
- **Title typo / 表記ゆれ guard (`--list-books`)**: because `book_id` is title-derived, a typo'd title silently creates a *duplicate* book. `--list-books` is a **read-only** mode that prints existing books (JSON) from the NotebookLM index via `split_per_book.list_books_from_index()`; add `--title "<q>"` to also get `matches_for_title` ranked by `find_similar_titles()` (difflib ratio over `normalize_title_for_match()` — NFKC-folded, lower-cased, whitespace/punctuation/symbol-stripped, so full/half-width and spacing variants score high; normalised-exact = 1.0). `--match-cutoff` (default `0.6`) tunes the threshold; `--matches-only` (with `--title`) omits the full `books` array so the assistant gets just the ranked matches. `find_similar_titles` returns `[]` for a degenerate (empty-normalized) query and skips empty-normalized candidates, so an all-symbol title can't spuriously score 1.0. The assistant runs this *before* writing to reconcile the user's title against existing books, then writes under the canonical title. `--list-books` runs before input-source validation, so `--list-books --title X` needs no `--highlight`. It requires Google Sheets configured (exits cleanly with a message otherwise; the skill falls back to confirming spelling with the user).
- Pure helpers (`build_notes_from_payload`, `summarize_plan`, `_coerce_books`, `_coerce_highlight`, `normalize_title_for_match`, `find_similar_titles`) are covered by `test/test_add_manual_highlights.py`; heavy deps (`main`, `notion`, `gspread`) are imported lazily inside the side-effecting functions so the module imports without them. Unicode-sensitive tests use `\uXXXX`-equivalent literals kept ASCII-safe so source encoding can't break them.
- **Shared operations (CLI ↔ web API, single source of truth)**: the side-effecting work lives in two print-free functions so both the CLI and `web/app.py` reuse it without duplication:
  - `build_books_result(title=None, *, match_cutoff, matches_only)` — read-only; loads config + reads the NotebookLM index via `split_per_book.list_books_from_index`, returns the same dict `--list-books` prints (`count` / optional `matches_for_title` / optional `books`). Raises `SheetsNotConfigured` if Sheets is off. `_run_list_books` is now a thin wrapper that prints it (and turns `SheetsNotConfigured` into a clean `SystemExit`).
  - `write_notes(notes, targets, *, apply)` — writes to `["Notion", "Google Sheets"]` (or a subset); the "Google Sheets" target now calls `split_per_book.sync_notes_to_notebooklm`. Returns `{"notion", "sheets", "problems"}` where each destination value is the writer's summary dict, `{"not_configured": True}` (Sheets targeted but unset), or `None` (not targeted / dry-run). The sync's `missing_files` are surfaced in `problems` (volume-missing = content not written; index-missing = catalogue stale). `apply=False` is a no-op (no heavy imports).
  - `SheetsNotConfigured(RuntimeError)` — raised when an op needs Sheets and it's off; CLI → `SystemExit`, web → `sheets_configured: false` JSON.
- The interactive flow (assistant reconciles the title via `--list-books` **or** `GET /api/manual/books`, asks for highlights, builds the JSON, dry-runs, confirms, applies via `--apply` **or** `POST /api/manual/highlights`) is encoded in the project skill `.claude/skills/adding-manual-highlights/SKILL.md`, which documents **three** execution modes: *Local CLI* (`py -m ...`), *Cloud mode* (run the same CLI as `python -m ...` inside a claude.ai/code cloud session connected to this repo, with secrets set as cloud env vars), and *HTTP API mode* (curl the deployed web service from anywhere).
- **Cloud mode (phone, no server) — `deploy/cloud_setup.sh`**: a setup script for the claude.ai/code cloud environment. It `pip install`s `requirements/requirements.txt` (the manual path needs no Playwright *browser*, only the pip wheel, since `import main` imports `playwright`). The user must set the env vars in the cloud environment (`NOTION_*`, `GOOGLE_SHEETS_*`, plus `AMAZON_EMAIL`/`AMAZON_PASSWORD` — still required by `main.load_config()` even though the manual path doesn't use them) and set network access to **Full** or allowlist `api.notion.com` (Google's `*.googleapis.com` is allowed by default). ⚠️ Cloud env vars have no dedicated secret store yet (semi-public to env editors) — note this when storing the service-account JSON / Notion key.
- Supporting facts: `save_notes_to_notion()` returns `{"added", "skipped", "failed", "total"}`; `split_per_book.sync_notes_to_notebooklm()` returns `{"new_books", "new_highlights", "skipped_duplicates", "skipped_invalid", "total_notes", "missing_files", "touched_volumes"}` (the first five keys match the retired `save_notes_to_google_sheets` so existing summary-printing code is unchanged); `split_per_book.list_books_from_index()` is the read-only catalogue reader; `note_utils.build_note_key_from_note()` falls back to `location` when `page` is empty (so a manual `location`-only highlight reaches Notion's `Page` property and dedup key). Kindle notes carry only `page`, so their Notion key is unchanged.

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
- **NotebookLM volumes**: dedup key is `(book_id, sha1(content))` (`content_dedup_key`); reconstructed per volume from the volume's existing rows before merging new notes
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
 
## Google Sheets Schema — current (NotebookLM 100-file layout)

The live Sheets data model is the 100-file layout written by `scripts/split_per_book.sync_notes_to_notebooklm`. Each file is a separate Google Sheets file in the `notebooklm/` Drive folder; only sheet 1 of each is used.

**Volume files** `<prefix>_vol_01`..`<prefix>_vol_99` — one row per highlight (self-describing): `book_id, book_title, highlight_id, location, content`.

**Index file** `<prefix>_index` — one row per book (book→file catalogue): `book_id, title, volume, highlight_count, last_synced_at`.

Keys: `book_id` = `BK-`+SHA1(title)[0:6]; `highlight_id` = `HL-<book6>-<NNNN>`; a book is pinned to a volume by `volume_for_book_id` = `SHA1(book_id) % 99 + 1`; dedup key `(book_id, sha1(content))`. The 100-file layout has **no metadata or `source` columns** — that data lives only in Notion. The user pre-creates the 100 empty files once (service accounts can't create Drive files); changing `VOLUME_COUNT`/`volume_for_book_id` requires the one-time `--redistribute` migration + a full NotebookLM re-import.

## Retired master schema (`01_books` / `02_highlights`) — historical only
 
These two worksheets were the old data store, written by the now-deprecated `google_sheets/toSheets.py`. **Nothing writes them anymore** (superseded by the 100-file layout above). They are documented only so the legacy `split_per_book --from-master` backfill and `migrate_legacy_sheet.py` remain intelligible.
 
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
1. `kindle2notion` no longer writes these — they are retired.
2. AI-populated sheets (`03`–`05`) are never read or modified.
3. Existing `book_id` / `highlight_id` values are never changed after initial write.
 
`scripts/migrate_legacy_sheet.py` (which targeted this retired master) is deprecated; do not run it on live data.
 
## Deployment (Render + Vercel + Turso)
 
The production topology is: **Vercel** serves `frontend/` statically (always-on entry
point), **Render** runs the Docker backend (Flask + Playwright), and **Turso** persists
the operational state. Files:
- `Dockerfile` — Python 3.12 + Playwright Chromium image; `CMD ["gunicorn", "-c", "gunicorn.conf.py", "web_main:app"]`
- `gunicorn.conf.py` — **1 gthread worker** (PipelineState / run_lock / SSE buffer are in-process; more workers would shard them), `timeout 0` (SSE streams must never be watchdog-killed), threads via `GUNICORN_THREADS`
- `.dockerignore` — keeps secrets/caches/local data (incl. `local_store.db`) out of the build context
- `render.yaml` — Render Blueprint: one web service, `healthCheckPath: /healthz`, secrets as `sync: false`
- `deploy/render/README.md` — backend guide (incl. Turso setup); `deploy/vercel/README.md` — frontend guide
 
Render-specific behaviour built into the code:
- `web_main.py` binds `PORT` (Render-injected) first, then `WEB_PORT`, then `5000`
- With `TURSO_*` set, the Amazon session survives cold starts/redeploys (hydrated from Turso), so the free plan no longer forces a 2FA re-login; `STORAGE_STATE_PATH` + a paid disk remain as an alternative
- `main.py` launches Chromium with `--no-sandbox --disable-dev-shm-usage` (`BROWSER_LAUNCH_ARGS`), required to run headless as root in a container
- `web/app.py` exposes `GET /healthz` (unauthenticated, exempt from Basic auth) for Render health checks and for the frontend's wake-up polling
- `CORS_ALLOWED_ORIGINS` must contain the Vercel origin for the cross-origin frontend to work
- Config still comes from env vars: `load_env_file()` is a no-op when `config/KEYS.env` is absent, so Render dashboard env vars are read directly
 
The VPS path (`deploy/README.md`) still works (`python web_main.py` under systemd) but the VPS is currently out of service; its GitHub Actions deploy is `workflow_dispatch`-only.
 
## Key Files to Ignore
 
The following are git-ignored and must not be committed:
- `config/KEYS.env` — credentials
- `storage_state.json` — browser session (auto-generated)
- `local_store.db` — local SQLite fallback of the operational store
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.pytest_tmp/` — caches
- `CODEX_KEY_CONTEXT.md` — Claude session context
 
## Testing Notes
 
- `test/test_amazon/test_login.py`: tests for `amazon/login.py`; uses a `FakePage` mock class and `monkeypatch.setattr` to inject responses. The login helpers deliberately use only the FakePage API surface (`query_selector` / `is_visible` / `wait_for_timeout` / `url`)
- `test/test_note_utils.py`: pure-function tests for `note_utils.py` (legacy helpers + v2 ID/row builders); no network access needed
- `test/test_storage.py`: AppStore + SQLite backend for real on `tmp_path`; Turso backend against a monkeypatched `requests.post` (pipeline encoding/decoding, retries, batching)
- `test/test_session_store.py` / `test/test_main_run.py` / `test/test_transformer.py` / `test/test_to_notion.py` / `test/test_web_app.py`: cover the session mirroring, run() control flow, XHR/DOM scraping + fallback, dedup cache semantics, and web routes/CORS/SSE respectively — all offline via fakes
- `test/compare_scrape_modes.py`: NOT a pytest module — a manual helper that scrapes the real account in both modes and diffs the notes (`py -3 -m test.compare_scrape_modes [max_books]`)
- `test/test_split_per_book.py`: tests for `scripts/split_per_book.py` — the pure helpers (filename sanitisation, grouping, row shaping, row↔dict parsers, `merge_notes_into_volume`, `merge_summaries`, `volumes_for_book_ids`) plus the `sync_notes_to_notebooklm` / `list_books_from_index` orchestrator with an in-memory fake Drive (no network)
- `test/test_add_manual_highlights.py`: pure-function tests for `scripts/add_manual_highlights.py` (payload parsing, note building, plan summary); the `build_books_result` / `write_notes` stubs patch `scripts.split_per_book.list_books_from_index` / `sync_notes_to_notebooklm` (no network access needed)
- The test directory is git-ignored; no CI pipeline exists
- When modifying `amazon/login.py`, update `test/test_amazon/test_login.py`
- When modifying `note_utils.py`, update `test/test_note_utils.py`
- When modifying the pure helpers in `scripts/split_per_book.py`, update `test/test_split_per_book.py`
 
## Common Gotchas
 
- **The `01_books`/`02_highlights` master is retired.** Highlights now sync straight into the NotebookLM 100-file layout via `split_per_book.sync_notes_to_notebooklm`. `google_sheets/toSheets.py` and `scripts/migrate_legacy_sheet.py` are deprecated; do not wire them into new code.
- **`split_per_book --from-master` is dangerous.** It reads the retired master and OVERWRITES all 100 files, clobbering any highlights added after the master was last updated. The default `split_per_book --apply` (no flag) only rebuilds the index from the volumes and is safe. Use `--from-master` solely for a one-time backfill from an old master.
- **The NotebookLM folder must be findable.** `sync_notes_to_notebooklm` resolves the folder via `NOTEBOOKLM_PARENT_FOLDER_ID` → (fallback) the master spreadsheet's Drive parent. Set `NOTEBOOKLM_PARENT_FOLDER_ID` in `config/KEYS.env` to **the folder that holds the 100 files** (or a parent containing a `notebooklm/` subfolder — both work). ⚠️ A common mistake is the OPPOSITE of what you'd guess: if you point the env var at the 100-file folder and the code can't find a `notebooklm/` subfolder inside it, it now correctly uses that folder directly (older builds reported all files as missing). If a volume/index file is genuinely missing it lands in the summary's `missing_files` and those highlights are NOT written (pre-create the 100 files once).
- The Amazon notebook URL targets Japan (`read.amazon.co.jp`). Do not change to `.com`.
- XHR mode may legitimately return MORE highlights than DOM mode for large books (DOM only reads the initially rendered chunk); dedup makes the difference safe. If Amazon changes the annotation endpoint, the run falls back to DOM mode automatically — check `run_history.scrape_mode` for `dom-fallback` to spot silent degradation.
- If `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` starts with `{`, it is treated as a raw JSON string, not a file path.
- `storage_state.json` is validated (not blindly trusted) at the start of each run; an invalid session degrades to a normal login. With Turso configured it is also mirrored remotely, newest-wins.
- The Notion dedup cache means hand-deleted Notion pages stay deleted; `scripts/resync_notion_cache.py` restores scan semantics. Never seed the cache from a lenient (partial) fetch — that is why `fetch_existing_note_keys_strict` exists.
- The GUI requires a display server (X11/Wayland). Running headlessly in CI will fail unless a virtual display is provided.
- Service accounts have **0 bytes of personal Drive storage**. They can edit files shared with them and create folders (0 bytes), but they cannot own new files in "My Drive" — Google rejects creation with `storageQuotaExceeded`. Workarounds: (a) Workspace Shared Drive, (b) OAuth user credentials, (c) pre-create files manually. `scripts/split_per_book.py` uses option (c).
- For files in "My Drive" root that are shared with the service account (not owned), the Drive API may return an empty `parents` field. `scripts/split_per_book.py` handles this via the `--parent-folder` CLI flag or the `NOTEBOOKLM_PARENT_FOLDER_ID` env var.
- A spreadsheet whose **parent folder was trashed** is still readable/writable by ID (the service account writes succeed), but it is invisible in the owner's normal Drive view and will be **permanently deleted** when the trash auto-purges (~30 days). If writes "succeed" but the user can't see them, check the file's `trashed` flag via the Drive API (`files.get?fields=trashed,explicitlyTrashed,parents`). This is exactly why the retired master should not be used as a parent-folder anchor: set `NOTEBOOKLM_PARENT_FOLDER_ID` (or `--parent-folder`) to the **live** folder that hosts the 100 NotebookLM files.