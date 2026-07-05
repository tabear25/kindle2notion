"""Best-effort run history recording for both entry points (GUI and web).

Lives at the top level so ``main.py`` and ``web/pipeline.py`` can share it
without an import cycle (both import this; this never imports them).
History must never fail a run: every store interaction is wrapped.
"""

from __future__ import annotations

from book_transformer import transformer
from storage import get_store_or_none


def record_run_start(mode):
    """Return ``(store, run_id)``; ``(None, None)`` when history is off."""
    store = get_store_or_none()
    if store is None:
        return None, None
    try:
        return store, store.record_run_start(mode)
    except Exception as exc:
        print(f"Warning: could not record run start: {exc}")
        return None, None


def record_run_end(store, run_id, **fields):
    if store is None or run_id is None:
        return
    try:
        store.record_run_end(run_id, **fields)
    except Exception as exc:
        print(f"Warning: could not record run end: {exc}")


def run_stats(notes, notion_summary=None, sheets_summary=None):
    """Shape writer summaries into run_history columns."""
    notion_summary = notion_summary or {}
    sheets_summary = sheets_summary or {}
    return {
        "scrape_mode": transformer.last_scrape_mode,
        "books": len({note.get("book_id") for note in notes if note.get("book_id")}),
        "highlights": len(notes),
        "notion_added": notion_summary.get("added"),
        "notion_skipped": notion_summary.get("skipped"),
        "notion_failed": notion_summary.get("failed"),
        "sheets_new_highlights": sheets_summary.get("new_highlights"),
    }
