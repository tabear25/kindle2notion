import os
from pathlib import Path

import nest_asyncio
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import amazon.login
from book_transformer import transformer
from gui_utils.gui import prompt_book_limit
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

required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
if not all(required_env_vars):
    raise ValueError(
        "Missing required environment variables. Please set AMAZON_EMAIL, AMAZON_PASSWORD, "
        "NOTION_API_KEY, and NOTION_DATABASE_ID in config/KEYS.env."
    )
def run(playwright, max_books=None):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD)
        context.storage_state(path=str(STORAGE_STATE_PATH))
    finally:
        browser.close()

    headless_browser = playwright.chromium.launch(headless=True)
    headless_context = headless_browser.new_context(storage_state=str(STORAGE_STATE_PATH))
    headless_page = headless_context.new_page()

    try:
        notes = transformer.extract_notes(headless_page, max_books=max_books)
        return notes
    finally:
        headless_browser.close()


if __name__ == "__main__":
    max_books = prompt_book_limit()
    with sync_playwright() as p:
        notes = run(p, max_books=max_books)
        toNotion.save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        print("Saved notes to Notion.")