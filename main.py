import os
import threading
from pathlib import Path

import nest_asyncio
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import amazon.login
from book_transformer import transformer
from gui_utils import gui
from gui_utils.gui import ask_book_limit
from notion import toNotion

nest_asyncio.apply()

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / "config" / "KEYS.env"
STORAGE_STATE_PATH = BASE_DIR / "storage_state.json"

load_dotenv(ENV_PATH)
AMAZON_EMAIL = os.getenv("AMAZON_EMAIL")
AMAZON_PASSWORD = os.getenv("AMAZON_PASSWORD")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE_ENV = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE")
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SHEETS_WORKSHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "Sheet1")

required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
if not all(required_env_vars):
    raise ValueError(
        "Missing required environment variables. Please set AMAZON_EMAIL, AMAZON_PASSWORD, "
        "NOTION_API_KEY, and NOTION_DATABASE_ID in config/KEYS.env."
    )

google_sheets_envs = [
    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE_ENV,
    GOOGLE_SHEETS_SPREADSHEET_ID,
]
GOOGLE_SHEETS_ENABLED = all(google_sheets_envs)
if any(google_sheets_envs) and not GOOGLE_SHEETS_ENABLED:
    raise ValueError(
        "Incomplete Google Sheets configuration. To enable Google Sheets export, set "
        "GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE and GOOGLE_SHEETS_SPREADSHEET_ID in config/KEYS.env."
    )

GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = None
if GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE_ENV:
    service_account_value = GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE_ENV.strip()
    if service_account_value.startswith("{"):
        GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = service_account_value
    else:
        service_account_value = service_account_value.strip("'\"")
        service_account_path = Path(service_account_value)
        if not service_account_path.is_absolute():
            service_account_path = BASE_DIR / service_account_path
        GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE = str(service_account_path)

def prompt_book_limit():
    return ask_book_limit()

def run(playwright, max_books=None, progress_callback=None, two_factor_prompt=None):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD,
                                   two_factor_prompt=two_factor_prompt)
        context.storage_state(path=str(STORAGE_STATE_PATH))
    finally:
        browser.close()

    headless_browser = playwright.chromium.launch(headless=True)
    headless_context = headless_browser.new_context(storage_state=str(STORAGE_STATE_PATH))
    headless_page = headless_context.new_page()

    try:
        notes = transformer.extract_notes(headless_page, max_books=max_books,
                                          progress_callback=progress_callback)
        return notes
    finally:
        headless_browser.close()

if __name__ == "__main__":
    max_books = prompt_book_limit()
    window = gui.ProgressWindow(total_books=max_books)

    def _worker():
        try:
            def two_factor_prompt():
                result_holder = [None]
                event = threading.Event()

                def _show():
                    result_holder[0] = gui.prompt_two_factor_code(parent=window._root)
                    event.set()

                window._root.after(0, _show)
                event.wait()
                return result_holder[0]

            with sync_playwright() as p:
                notes = run(p, max_books=max_books, progress_callback=window.update,
                            two_factor_prompt=two_factor_prompt)
            toNotion.save_notes_to_notion(
                NOTION_API_KEY, NOTION_DATABASE_ID, notes,
                progress_callback=window.update,
            )
            print("Saved notes to Notion.")
            if GOOGLE_SHEETS_ENABLED:
                from google_sheets import toSheets

                toSheets.save_notes_to_google_sheets(
                    GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
                    GOOGLE_SHEETS_SPREADSHEET_ID,
                    GOOGLE_SHEETS_WORKSHEET_NAME,
                    notes,
                    progress_callback=window.update,
                )
                print("Saved notes to Google Sheets.")
            window.mark_done()
        except Exception as e:
            window.mark_error(str(e))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    window.run()