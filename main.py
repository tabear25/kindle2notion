import os
import threading
from pathlib import Path

import nest_asyncio
from playwright.sync_api import sync_playwright

import amazon.login
from book_transformer import transformer
from config import BASE_DIR, load_env_file
from notion import toNotion
from storage import get_store_or_none
from storage.session_store import hydrate_session_file, persist_session_file

nest_asyncio.apply()
load_env_file()

STORAGE_STATE_PATH = Path(os.getenv("STORAGE_STATE_PATH") or BASE_DIR / "storage_state.json")
BROWSER_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

_config_loaded = False
AMAZON_EMAIL = None
AMAZON_PASSWORD = None
NOTION_API_KEY = None
NOTION_DATABASE_ID = None
GOOGLE_SHEETS_ENABLED = False
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = None
GOOGLE_SHEETS_SPREADSHEET_ID = None


def load_config():
    """Load and validate configuration from KEYS.env. Safe to call multiple times."""
    global _config_loaded
    global AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID
    global GOOGLE_SHEETS_ENABLED, GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE
    global GOOGLE_SHEETS_SPREADSHEET_ID

    if _config_loaded:
        return

    load_env_file()
    AMAZON_EMAIL = os.getenv("AMAZON_EMAIL")
    AMAZON_PASSWORD = os.getenv("AMAZON_PASSWORD")
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
    google_sheets_saf_env = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE")
    GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")

    required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
    if not all(required_env_vars):
        raise ValueError(
            "Missing required environment variables. Please set AMAZON_EMAIL, AMAZON_PASSWORD, "
            "NOTION_API_KEY, and NOTION_DATABASE_ID in config/KEYS.env."
        )

    google_sheets_envs = [google_sheets_saf_env, GOOGLE_SHEETS_SPREADSHEET_ID]
    GOOGLE_SHEETS_ENABLED = all(google_sheets_envs)
    if any(google_sheets_envs) and not GOOGLE_SHEETS_ENABLED:
        raise ValueError(
            "Incomplete Google Sheets configuration. To enable Google Sheets export, set "
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE and GOOGLE_SHEETS_SPREADSHEET_ID in config/KEYS.env."
        )

    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = None
    if google_sheets_saf_env:
        service_account_value = google_sheets_saf_env.strip()
        if service_account_value.startswith("{"):
            GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = service_account_value
        else:
            service_account_value = service_account_value.strip("'\"")
            service_account_path = Path(service_account_value)
            if not service_account_path.is_absolute():
                service_account_path = BASE_DIR / service_account_path
            GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = str(service_account_path)

    _config_loaded = True


def prompt_book_limit():
    from gui_utils.gui import ask_book_limit
    return ask_book_limit()


def run(playwright, max_books=None, progress_callback=None,
        two_factor_callback=None, headless_login=False):
    load_config()
    store = get_store_or_none()
    hydrate_session_file(store, STORAGE_STATE_PATH)

    browser = playwright.chromium.launch(headless=True, args=BROWSER_LAUNCH_ARGS)
    try:
        # Fast path: a saved session that still reaches the notebook skips
        # the whole login (and 2FA) and scrapes right away.
        if STORAGE_STATE_PATH.exists():
            context = browser.new_context(storage_state=str(STORAGE_STATE_PATH))
            page = context.new_page()
            if amazon.login.is_session_valid(page):
                notes = transformer.extract_notes(page, max_books=max_books,
                                                  progress_callback=progress_callback)
                persist_session_file(context, store, STORAGE_STATE_PATH)
                return notes
            context.close()

        if headless_login:
            # Web mode: log in headless in a fresh context of the same
            # browser, then scrape in that authenticated context.
            context = browser.new_context()
            page = context.new_page()
            amazon.login.perform_login(
                page,
                AMAZON_EMAIL,
                AMAZON_PASSWORD,
                two_factor_callback=two_factor_callback,
                allow_manual_auth=False,
            )
            persist_session_file(context, store, STORAGE_STATE_PATH)
            notes = transformer.extract_notes(page, max_books=max_books,
                                              progress_callback=progress_callback)
            persist_session_file(context, store, STORAGE_STATE_PATH)
            return notes
    finally:
        browser.close()

    # GUI mode with no usable session: visible browser for the login (2FA
    # dialog / manual auth on the page), then scrape headless as before.
    login_browser = playwright.chromium.launch(headless=False, args=BROWSER_LAUNCH_ARGS)
    try:
        login_context = login_browser.new_context()
        login_page = login_context.new_page()
        amazon.login.perform_login(
            login_page,
            AMAZON_EMAIL,
            AMAZON_PASSWORD,
            two_factor_callback=two_factor_callback,
            allow_manual_auth=True,
        )
        persist_session_file(login_context, store, STORAGE_STATE_PATH)
    finally:
        login_browser.close()

    headless_browser = playwright.chromium.launch(headless=True, args=BROWSER_LAUNCH_ARGS)
    try:
        headless_context = headless_browser.new_context(storage_state=str(STORAGE_STATE_PATH))
        headless_page = headless_context.new_page()
        notes = transformer.extract_notes(headless_page, max_books=max_books,
                                          progress_callback=progress_callback)
        persist_session_file(headless_context, store, STORAGE_STATE_PATH)
        return notes
    finally:
        headless_browser.close()

if __name__ == "__main__":
    from gui_utils import gui

    load_config()
    max_books = prompt_book_limit()
    window = gui.ProgressWindow(total_books=max_books)

    def _worker():
        from book_transformer import transformer as _transformer
        from run_history import record_run_end, record_run_start, run_stats

        store, run_id = record_run_start("gui")
        try:
            with sync_playwright() as p:
                notes = run(
                    p,
                    max_books=max_books,
                    progress_callback=window.update,
                    two_factor_callback=window.prompt_two_factor_code,
                )
            notion_summary = toNotion.save_notes_to_notion(
                NOTION_API_KEY, NOTION_DATABASE_ID, notes,
                progress_callback=window.update,
            )
            print("Saved notes to Notion.")
            sheets_summary = None
            if GOOGLE_SHEETS_ENABLED:
                from scripts import split_per_book

                sheets_summary = split_per_book.sync_notes_to_notebooklm(
                    notes, apply=True, progress_callback=window.update,
                )
                print(
                    "Synced notes to NotebookLM volumes: "
                    f"+{sheets_summary['new_highlights']} highlights, "
                    f"+{sheets_summary['new_books']} books."
                )
                if sheets_summary["missing_files"]:
                    print(
                        "  [warning] missing NotebookLM file(s) (NOT written): "
                        + ", ".join(sheets_summary["missing_files"])
                    )
            record_run_end(
                store, run_id, status="done",
                **run_stats(notes, notion_summary, sheets_summary),
            )
            window.mark_done()
        except KeyboardInterrupt:
            raise
        except BaseException as e:
            record_run_end(
                store, run_id, status="error", error=str(e),
                scrape_mode=_transformer.last_scrape_mode,
            )
            window.mark_error(str(e))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    window.run()