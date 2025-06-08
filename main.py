import os
import asyncio
import nest_asyncio
nest_asyncio.apply()
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import amazon.login
from book_transformer import transformer
from notion import toNotion
from gui_utils.gui import show_popup_message
from pathlib import Path

env_path = Path(__file__).resolve().parent / 'config' / 'KEYS.env'
load_dotenv(dotenv_path=env_path)

AMAZON_EMAIL = os.getenv('AMAZON_EMAIL')
AMAZON_PASSWORD = os.getenv('AMAZON_PASSWORD')
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
missing = [k for k, v in enumerate(required_env_vars) if not v]
if missing:
    raise ValueError("必要な環境変数が設定されていません: {', '.join(missing)}")


def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        asyncio.run(amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD))
        context.storage_state(path="storage_state.json")
    finally:
        browser.close()

    headless_browser = playwright.chromium.launch(headless=True)
    headless_context = headless_browser.new_context(storage_state="storage_state.json")
    headless_page = headless_context.new_page()

    try:
        notes = transformer.extract_notes(headless_page)
        return notes
    finally:
        headless_browser.close()

if __name__ == '__main__':
    with sync_playwright() as p:
        notes = run(p)
        toNotion.save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        show_popup_message("Notionへの保存が完了しました。", title="完了")