# CLAUDE.md

This file provides guidance for AI assistants working on the kindle2notion codebase.

## Project Overview

kindle2notion is a Python automation tool that scrapes Kindle highlights from the Amazon Kindle notebook page (Japan: `read.amazon.co.jp/notebook`) and exports them to a Notion database. Optionally, highlights can also be exported to Google Sheets.

The application uses Playwright for browser automation, the official Notion Python SDK, and a Tkinter-based GUI for user interaction (book limit selection, 2FA code entry).

## Repository Structure

```
kindle2notion/
├── main.py                         # Application entry point and orchestrator
├── __init__.py                     # Package marker
├── amazon/
│   ├── __init__.py
│   └── login.py                    # Amazon authentication via Playwright
├── book_transformer/
│   ├── __init__.py
│   └── transformer.py              # Kindle highlight extraction logic
├── config/
│   ├── __init__.py
│   └── KEYS.env                    # Credentials file (git-ignored, must be created manually)
├── google_sheets/
│   ├── __init__.py
│   └── toSheets.py                 # Google Sheets export module
├── gui_utils/
│   ├── __init__.py
│   └── gui.py                      # Tkinter GUI dialogs
├── notion/
│   ├── __init__.py
│   └── toNotion.py                 # Notion database export module
├── requirements/
│   └── requirements.txt            # Python package dependencies
└── test/
    └── test_amazon/
        └── login.py                # pytest tests for the login module
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

# Optional (enable Google Sheets export by setting all three)
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=/path/to/service_account.json
GOOGLE_SHEETS_SPREADSHEET_ID=...
GOOGLE_SHEETS_WORKSHEET_NAME=Sheet1
```

`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` can be either a file path or a raw JSON string starting with `{`.

### Running the Application

```bash
python main.py
```

The app will:
1. Show a GUI dialog to enter the number of books to process (or leave blank for all)
2. Open a non-headless Chromium browser for Amazon login (including 2FA if prompted)
3. Save the browser session to `storage_state.json`
4. Scrape highlights in a headless browser session
5. Save highlights to Notion (and optionally Google Sheets)

## Running Tests

```bash
pytest test/
```

Tests use pytest with monkeypatching. There is no separate test runner script. The test directory is git-ignored, so tests exist only locally.

## Application Flow

```
main.py
  └── prompt_book_limit()          # GUI: ask how many books to process
  └── run(playwright, max_books)
        ├── amazon.login.perform_login()     # Non-headless: login, handle 2FA
        ├── context.storage_state()          # Save session to storage_state.json
        └── book_transformer.extract_notes() # Headless: scrape highlights
  └── toNotion.save_notes_to_notion()        # Always runs
  └── toSheets.save_notes_to_google_sheets() # Only if GOOGLE_SHEETS_ENABLED
```

## Core Data Structure

All modules pass highlights around as a list of dictionaries:

```python
{
    "title": "Book Title",   # str: book title from h3 element
    "content": "...",        # str: highlight text (used as dedup key)
    "page": "42"             # str: page number extracted via regex (may be "")
}
```

## Module Responsibilities

### `main.py`
- Loads and validates environment variables from `config/KEYS.env`
- Determines if Google Sheets export is enabled
- Resolves the service account file path (supports relative and absolute paths, or raw JSON)
- Orchestrates the full execution pipeline

### `amazon/login.py`
- Navigates to `https://read.amazon.co.jp/notebook`
- Fills email and password fields using CSS selectors
- Handles optional 2FA via `prompt_two_factor_code()` GUI dialog
- Raises `Exception` if login fails (URL does not start with `AMAZON_NOTEBOOK_URL`)
- Uses `PlaywrightTimeoutError` handling: if 2FA selector is absent, skips 2FA step silently
- Key constants: `LOAD_TIMEOUT = 15000`, `IDLE = "networkidle"`

### `book_transformer/transformer.py`
- Iterates `.kp-notebook-library-each-book` elements
- Clicks each book and waits 5 seconds (`time.sleep(5)`) for content to load
- Extracts title from `h3`, highlights from `#highlight`, page numbers from `#annotationHighlightHeader` via regex
- Returns a list of note dicts

### `notion/toNotion.py`
- `get_existing_contents()`: paginates through all Notion DB entries (100/page) to build a dedup set
- `save_notes_to_notion()`: skips notes already in Notion (by `content` field), creates pages with `Title`, `Content`, `Page` rich_text/title properties
- Shows a tqdm progress bar during save

### `google_sheets/toSheets.py`
- `_build_client()`: supports service account JSON as a file path or raw JSON string
- `_get_or_create_worksheet()`: gets an existing worksheet or creates a new one
- `_ensure_header_row()`: adds `["Title", "Content", "Page"]` header if column A row 1 is empty
- Deduplication based on column B (Content)
- Appends rows in a batch with `RAW` input option

### `gui_utils/gui.py`
- All dialogs are built with Tkinter using a custom blue/gray color scheme
- `ask_book_limit()`: returns `int` or `None` (process all books)
- `prompt_two_factor_code()`: returns the 2FA code string, or `None` if cancelled
- Private helpers use underscore prefix (`_build_window`, `_center_window`, etc.)
- Font: Yu Gothic UI; Accent color: `#0ea5e9`

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
- Both Notion and Sheets modules use the `content` field as the dedup key
- Existing content is fetched into a `set` before writing, then each note is checked before insertion

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

## Google Sheets Schema

| Column A | Column B        | Column C |
|----------|-----------------|----------|
| Title    | Content (dedup) | Page     |

The header row is created automatically if missing.

## Key Files to Ignore

The following are git-ignored and must not be committed:
- `config/KEYS.env` — credentials
- `storage_state.json` — browser session (auto-generated)
- `__pycache__/`, `*.pyc` — Python cache
- `CODEX_KEY_CONTEXT.md` — Claude session context

## Testing Notes

- Tests live in `test/test_amazon/login.py` and use `pytest`
- `FakePage` is a mock class that records all Playwright page actions
- Monkeypatching (`monkeypatch.setattr`) is used to inject mock GUI responses
- The test directory is git-ignored; no CI pipeline exists
- When modifying `amazon/login.py`, update the corresponding tests in `test/test_amazon/login.py`

## Common Gotchas

- The Amazon notebook URL targets Japan (`read.amazon.co.jp`). Do not change to `.com`.
- `time.sleep(5)` between book clicks is intentional — the page loads highlights dynamically.
- If `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` starts with `{`, it is treated as a raw JSON string, not a file path.
- `storage_state.json` is reused on the next run if it already exists (no explicit expiry logic).
- The GUI requires a display server (X11/Wayland). Running headlessly in CI will fail unless a virtual display is provided.
