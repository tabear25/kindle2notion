import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# AmazonとBook Transformerのスクリプトは、以下ディレクトリ構成を想定してる例
import amazon.login
import book_transformer
from toNotion import save_notes_to_notion

# 必要な関数だけを一度だけインポート
from toNotion import save_notes_to_notion

load_dotenv('config/KEYS.env')
AMAZON_EMAIL = os.getenv('AMAZON_EMAIL')
AMAZON_PASSWORD = os.getenv('AMAZON_PASSWORD')
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
if not all(required_env_vars):
    raise ValueError("必要な環境変数が設定されていないで。KEYS.env内に必要な情報が入力されてるか確認してな。")

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Amazonログイン実施
        amazon.login.perform_login(page, AMAZON_EMAIL, AMAZON_PASSWORD)
        # ハイライトしたノートなどを抽出
        notes = book_transformer.extract_notes(page)
        return notes
    finally:
        browser.close()

if __name__ == '__main__':
    with sync_playwright() as p:
        notes = run(p)
        # ここでNotionに保存
        save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        print("Notionへの保存が完了したで。")
