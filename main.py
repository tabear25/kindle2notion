import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import argparse

import amazon.login
from book_transformer import transformer
from notion import toNotion
from gui_utils.gui import show_popup_message, ask_book_limit
from pathlib import Path

env_path = Path(__file__).resolve().parent / 'config' / 'KEYS.env'
load_dotenv(dotenv_path=env_path)

AMAZON_EMAIL = os.getenv('AMAZON_EMAIL')
AMAZON_PASSWORD = os.getenv('AMAZON_PASSWORD')
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

env_names = ['AMAZON_EMAIL', 'AMAZON_PASSWORD', 'NOTION_API_KEY', 'NOTION_DATABASE_ID']
env_values = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
missing = [name for name, val in zip(env_names, env_values) if not val]
if missing:
    raise ValueError(f"必要な環境変数が設定されていません: {', '.join(missing)}")


def run(playwright, limit: int = 3):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD)
        notes = transformer.extract_notes(page, max_books=limit)
        return notes
    finally:
        browser.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch Kindle highlights to Notion')
    parser.add_argument('--limit', type=int, help='Number of books to process (overrides GUI input)')
    args = parser.parse_args()

    limit = args.limit if args.limit is not None else ask_book_limit()

    with sync_playwright() as p:
        notes = run(p, limit)
        toNotion.save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        show_popup_message("Notionへの保存が完了しました。", title="完了")
