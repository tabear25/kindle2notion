from notion_client import Client
from tqdm import tqdm

from note_utils import build_note_key, build_note_key_from_note, note_key_hash
from notion import dedup_cache
from storage import get_store_or_none

# How many freshly created page hashes to buffer before flushing them to the
# dedup cache mid-run (plus a final flush), bounding what a crash can lose.
DEDUP_FLUSH_EVERY = 100


def _extract_plain_text(items):
    return "".join(
        (item.get("plain_text") or item.get("text", {}).get("content", ""))
        for item in items
    ).strip()


def fetch_existing_note_keys_strict(notion_api_key, database_id, into=None):
    """Paginate the full database into a set of (title, content, page) keys.

    Raises on any API error — used to seed the dedup cache, where a silent
    partial result would poison the cache and cause duplicates later.
    ``into`` lets the lenient wrapper keep whatever was collected before a
    mid-pagination failure.
    """
    existing_note_keys = into if into is not None else set()
    notion = Client(auth=notion_api_key)

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

    return existing_note_keys


def get_existing_note_keys(notion_api_key, database_id):
    """Legacy lenient variant: returns what it could fetch, never raises."""
    existing_note_keys = set()
    try:
        fetch_existing_note_keys_strict(notion_api_key, database_id, into=existing_note_keys)
    except Exception as e:
        print(f"Failed to fetch existing notes from Notion: {e}")
    return existing_note_keys


def save_notes_to_notion(notion_api_key, database_id, notes, progress_callback=None,
                         force_resync=False):
    """Create Notion pages for new notes, skipping duplicates.

    Dedup keys come from the operational store's cache when available (one
    query instead of paginating the whole database each run); otherwise this
    falls back to the legacy full scan. ``force_resync=True`` rebuilds the
    cache from Notion first, restoring pure-scan semantics for that run.

    Returns a summary dict ``{"added", "skipped", "failed", "total"}``.
    Existing callers (GUI / web pipeline) ignore the return value; manual-entry
    tooling uses it to report what was written.
    """
    notion = Client(auth=notion_api_key)

    store = get_store_or_none()
    cached_hashes = dedup_cache.load_dedup_hashes(
        store, notion_api_key, database_id, force_resync=force_resync
    )
    cache_active = cached_hashes is not None
    if cache_active:
        known_hashes = cached_hashes
    else:
        known_hashes = {
            note_key_hash(key)
            for key in get_existing_note_keys(notion_api_key, database_id)
        }

    added = 0
    skipped = 0
    failed = 0
    pending_hashes = []

    try:
        for i, note in enumerate(tqdm(notes, desc="Notion")):
            if progress_callback:
                progress_callback("notion", i + 1, len(notes), note.get("title", ""))

            note_key = build_note_key_from_note(note)
            key_hash = note_key_hash(note_key)
            if key_hash in known_hashes:
                skipped += 1
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
                known_hashes.add(key_hash)
                added += 1
                if cache_active:
                    pending_hashes.append(key_hash)
                    if len(pending_hashes) >= DEDUP_FLUSH_EVERY:
                        dedup_cache.record_new_hashes(store, database_id, pending_hashes)
                        pending_hashes = []
            except Exception as e:
                failed += 1
                print(f"Failed to save note to Notion: {content} ({e})")
    finally:
        if cache_active and pending_hashes:
            dedup_cache.record_new_hashes(store, database_id, pending_hashes)

    return {
        "added": added,
        "skipped": skipped,
        "failed": failed,
        "total": len(notes),
    }
