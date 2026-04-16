from notion_client import Client
from tqdm import tqdm

from note_utils import build_note_key, build_note_key_from_note


def _extract_plain_text(items):
    return "".join(
        (item.get("plain_text") or item.get("text", {}).get("content", ""))
        for item in items
    ).strip()


def get_existing_note_keys(notion_api_key, database_id):
    notion = Client(auth=notion_api_key)
    existing_note_keys = set()

    try:
        response = notion.databases.query(database_id=database_id, page_size=100)
        while True:
            for page in response.get("results", []):
                properties = page.get("properties", {})
                title = _extract_plain_text(properties.get("Title", {}).get("title", []))
                content = _extract_plain_text(properties.get("Content", {}).get("rich_text", []))
                page_number = _extract_plain_text(properties.get("Page", {}).get("rich_text", []))
                if title or content or page_number:
                    existing_note_keys.add(build_note_key(title, content, page_number))

            if response.get("has_more"):
                response = notion.databases.query(
                    database_id=database_id,
                    start_cursor=response.get("next_cursor"),
                    page_size=100,
                )
            else:
                break
    except Exception as e:
        print(f"Failed to fetch existing notes from Notion: {e}")

    return existing_note_keys


def save_notes_to_notion(notion_api_key, database_id, notes, progress_callback=None):
    notion = Client(auth=notion_api_key)
    existing_note_keys = get_existing_note_keys(notion_api_key, database_id)

    for i, note in enumerate(tqdm(notes, desc="Notion")):
        if progress_callback:
            progress_callback("notion", i + 1, len(notes), note.get("title", ""))

        note_key = build_note_key_from_note(note)
        if note_key in existing_note_keys:
            continue

        title, content, page_number = note_key
        try:
            notion.pages.create(
                parent={"database_id": database_id},
                properties={
                    "Title": {
                        "title": [{"text": {"content": title}}],
                    },
                    "Content": {
                        "rich_text": [{"text": {"content": content}}],
                    },
                    "Page": {
                        "rich_text": [{"text": {"content": page_number}}],
                    },
                },
            )
            existing_note_keys.add(note_key)
        except Exception as e:
            print(f"Failed to save note to Notion: {content} ({e})")
