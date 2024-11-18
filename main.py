import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from toNotion import save_notes_to_notion  
import amazon.login 
import book_transformer
import toNotion
from toNotion.toNotion import save_notes_to_notion

load_dotenv('KEYS.env')
AMAZON_EMAIL = os.getenv('AMAZON_EMAIL')
AMAZON_PASSWORD = os.getenv('AMAZON_PASSWORD')
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
if not all(required_env_vars):
    raise ValueError("必要な環境変数が設定されていません。KEYS.env内に必要な情報が入力されているのかを確認してください。")

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD)
        notes = book_transformer.extract_notes(page)
        return notes
    finally:
        browser.close()

if __name__ == '__main__':
    with sync_playwright() as p:
        notes = run(p)

        toNotion.save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        print("Notionへの保存が完了しました。")