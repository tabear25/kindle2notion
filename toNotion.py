# toNotion.py

import os
from notion_client import Client

def get_existing_contents(notion_api_key, database_id):
    """
    Notionデータベースから既存のコンテンツを取得します。
    """
    notion = Client(auth=notion_api_key)
    existing_contents = set()
    
    try:
        response = notion.databases.query(database_id=database_id, page_size=100)
        while True:
            for page in response.get('results', []):
                properties = page.get('properties', {})
                content_list = properties.get('Content', {}).get('rich_text', [])
                if content_list:
                    content = content_list[0].get('text', {}).get('content', '')
                    if content:
                        existing_contents.add(content)
            if response.get('has_more'):
                response = notion.databases.query(
                    database_id=database_id,
                    start_cursor=response.get('next_cursor'),
                    page_size=100
                )
            else:
                break
    except Exception as e:
        print(f"Notionから既存のコンテンツを取得中にエラーが発生しました: {e}")
    
    return existing_contents

def save_notes_to_notion(notion_api_key, database_id, notes):
    """
    取得したノートをNotionデータベースに保存します。既存のノートは重複しないようにします。
    """
    # Notionクライアントの初期化
    notion = Client(auth=notion_api_key)

    # 既存のノートのcontentを取得
    existing_contents = get_existing_contents(notion_api_key, database_id)

    # 重複していないノートだけをNotionに追加
    for note in notes:
        if note['content'] in existing_contents:
            print(f"'{note['content']}' はすでに存在します。追加されません。")
            continue

        try:
            new_page = {
                "parent": {"database_id": database_id},
                "properties": {
                    "Title": {
                        "title": [
                            {
                                "text": {
                                    "content": note['title']
                                }
                            }
                        ]
                    },
                    "Content": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": note['content']
                                }
                            }
                        ]
                    },
                    "Page": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": note.get('page', '')  # 'page'がない場合は空文字
                                }
                            }
                        ]
                    }
                }
            }
            notion.pages.create(**new_page)
            print(f"'{note['content']}' をNotionに追加しました。")
        except Exception as e:
            print(f"Notionへの保存中にエラーが発生しました: {e}")

    print("すべてのノートがNotionに保存されました。")