import os
from notion_client import Client

def get_existing_contents(notion_api_key, database_id):
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
    notion = Client(auth=notion_api_key)

    existing_contents = get_existing_contents(notion_api_key, database_id)

    for note in notes:

        if note['content'] in existing_contents:
            print(f"'{note['content']}' はすでに存在します。追加されません。")
            continue
        
        page_number_value = note.get('page', '')
        if page_number_value and page_number_value.isdigit():
            page_number = int(page_number_value)
        else:
            page_number = None

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
                        "number": page_number
                    }
                }
            }
            notion.pages.create(**new_page)
        except Exception as e:
            print(f"Notionへの保存中にエラーが発生しました。'{note['content']}'を追加する際にエラーが発生しています。: {e}")