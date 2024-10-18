import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from toNotion import save_notes_to_notion  

# 環境変数の読み込み
load_dotenv('IDPW.env')

# 環境変数からIDとパスワード、Notion APIキーを取得する
AMAZON_EMAIL = os.getenv('AMAZON_EMAIL')
AMAZON_PASSWORD = os.getenv('AMAZON_PASSWORD')
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

# 環境変数に必要事項が入っていなかった場合のハンドリング
required_env_vars = [AMAZON_EMAIL, AMAZON_PASSWORD, NOTION_API_KEY, NOTION_DATABASE_ID]
if not all(required_env_vars):
    raise ValueError("必要な環境変数が設定されていません。IDPW.env内に必要な情報が入力されているのかを確認してください。")

def run(playwright):
    # ブラウザをヘッドレスモードで起動（必要に応じてheadless=Trueに変更可能）
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto("https://read.amazon.co.jp/notebook", timeout=60000)

        # ログインフォームに入力
        page.fill('input#ap_email', AMAZON_EMAIL)
        page.click('input#continue')

        # パスワード入力ページがロードされるまで待機
        page.wait_for_selector('input#ap_password', timeout=10000)

        page.fill('input#ap_password', AMAZON_PASSWORD)
        page.click('input#signInSubmit')

        # 2段階認証画面が表示された場合の対応
        print('ログインのために2段階認証コードを入力してください。60秒待機します。')
        page.wait_for_timeout(60000)  # 60秒待機

        # ログインが成功したか確認
        page.wait_for_load_state('networkidle')
        if not page.url.startswith("https://read.amazon.co.jp/notebook"):
            raise Exception("Amazonへのログインに失敗しました。")

        print("Amazonへのログインに成功しました。")

        # 全ての本の要素を取得
        each_books = page.query_selector_all('.kp-notebook-library-each-book')

        notes = []  # Notionに保存するためのノートリストを追加

        for index, book in enumerate(each_books):
            text_array = []

            # 各々の本をクリックすることによって、そのハイライトを表示する
            book.click()
            time.sleep(7)  

            # 書籍名の取得を試みる
            book_title_element = page.query_selector('h3')
            if book_title_element:
                book_title = book_title_element.text_content().strip()
            else:
                book_title = f"Unknown Book {index + 1}"
                print(f"警告: 書籍 {index + 1} のタイトルが見つかりませんでした。")

            # ハイライトを取り出す
            highlights = page.query_selector_all('#highlight')

            for highlight in highlights:
                content = highlight.text_content().strip()
                text_array.append(content)
                # Notionに保存するためのノートを作成
                note = {
                    "title": book_title,
                    "content": content,
                    "page": ""  
                }
                notes.append(note)

        return notes
    finally:
        browser.close()

if __name__ == '__main__':
    with sync_playwright() as p:
        notes = run(p)

        # Notionに保存
        save_notes_to_notion(NOTION_API_KEY, NOTION_DATABASE_ID, notes)
        print("Notionへの保存が完了しました。")