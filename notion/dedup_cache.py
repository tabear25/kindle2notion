"""Cache of Notion dedup key hashes in the operational store.

Replaces the per-run full pagination of the Notion database: the key set is
fetched from Notion once (seed), then loaded from the store in a single query
and appended to as pages are created. Every integrity failure converges on
"reseed from Notion", so a broken cache can never cause duplicate pages.

Behavior change vs. the pure scan (documented in the README): a page deleted
by hand in Notion stays deleted on later syncs instead of being re-added.
Run ``py -3 -m scripts.resync_notion_cache`` (or start a web run with
"full resync") to rebuild the cache and restore the old semantics on demand.

``NOTION_DEDUP_MODE=scan`` disables the cache entirely.
"""

from __future__ import annotations

import os

from note_utils import note_key_hash

NOTION_DEDUP_MODE_ENV = "NOTION_DEDUP_MODE"


def cache_enabled() -> bool:
    return (os.getenv(NOTION_DEDUP_MODE_ENV) or "cache").strip().lower() != "scan"


def load_dedup_hashes(store, notion_api_key, database_id, force_resync=False):
    """Return the known key-hash set, seeding from Notion when needed.

    Returns ``None`` when caching is disabled or unavailable — the caller
    then falls back to the legacy full scan.
    """
    if store is None or not cache_enabled():
        return None
    try:
        if force_resync or not store.is_seeded(database_id):
            return resync(store, notion_api_key, database_id)
        hashes = store.get_dedup_hashes(database_id)
        print(f"Notion dedup cache: {len(hashes)} keys loaded (no full scan).")
        return hashes
    except Exception as exc:
        print(f"Warning: dedup cache unavailable ({exc}); using a full Notion scan.")
        return None


def resync(store, notion_api_key, database_id):
    """Rebuild the cache from the live Notion database (strict fetch)."""
    from notion import toNotion

    keys = toNotion.fetch_existing_note_keys_strict(notion_api_key, database_id)
    hashes = {note_key_hash(key) for key in keys}
    store.seed_dedup_hashes(database_id, hashes)
    print(f"Seeded Notion dedup cache: {len(hashes)} keys.")
    return hashes


def record_new_hashes(store, database_id, hashes) -> None:
    """Append hashes of newly created pages; on failure, poison the cache.

    ``mark_dirty`` guarantees the next load reseeds from Notion, so a lost
    append can only cost one extra full scan — never a duplicate page.
    """
    hashes = list(hashes)
    if store is None or not hashes:
        return
    try:
        store.append_dedup_hashes(database_id, hashes)
    except Exception as exc:
        print(f"Warning: could not extend the dedup cache ({exc}); flagging it for reseed.")
        try:
            store.mark_dirty(database_id)
        except Exception as dirty_exc:
            print(
                "Warning: could not flag the dedup cache as dirty "
                f"({dirty_exc}). Run scripts.resync_notion_cache before the "
                "next sync to avoid duplicate Notion pages."
            )
