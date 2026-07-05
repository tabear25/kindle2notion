"""Rebuild the Notion dedup cache from the live database.

Usage:
    py -3 -m scripts.resync_notion_cache

Use this after deleting pages by hand in Notion when you want the next sync
to re-add them (the cache otherwise remembers them as already synced), or
whenever the cache is suspected to be out of step with the database.
"""

from __future__ import annotations


def main_cli() -> int:
    import main as app_main

    app_main.load_config()

    from notion import dedup_cache
    from storage import get_store

    store = get_store()
    hashes = dedup_cache.resync(
        store, app_main.NOTION_API_KEY, app_main.NOTION_DATABASE_ID
    )
    print(f"[ok] Notion dedup cache rebuilt on {store.backend_name}: {len(hashes)} keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
