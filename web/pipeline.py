import threading
import traceback

from playwright.sync_api import sync_playwright

import main
from book_transformer import transformer
from notion import toNotion
from run_history import record_run_end, record_run_start, run_stats


class PipelineState:
    """Shared state between the pipeline worker thread and Flask routes.

    Pushes SSE-style events that the ``/api/events`` endpoint streams to the
    browser.  The 2FA bridge uses :class:`threading.Event` so the Playwright
    thread blocks until the user submits a code via the web form.
    """

    def __init__(self):
        self.events = []
        self.status = "idle"  # idle | running | waiting_2fa | done | error
        self._lock = threading.Lock()
        self._two_factor_event = threading.Event()
        self._two_factor_code = None

    # ------------------------------------------------------------------
    # 2FA bridge
    # ------------------------------------------------------------------

    def request_two_factor(self, error_message=None):
        """Called from the Playwright thread.  Blocks until a code arrives."""
        self.status = "waiting_2fa"
        self._push_event("2fa_required", {"error_message": error_message})
        self._two_factor_event.clear()
        self._two_factor_event.wait(timeout=300)  # 5 min
        code = self._two_factor_code
        self._two_factor_code = None
        if code is None:
            return None
        self.status = "running"
        return code

    def submit_two_factor(self, code):
        """Called from the Flask route when the user submits a 2FA code."""
        self._two_factor_code = code
        self._two_factor_event.set()

    # ------------------------------------------------------------------
    # Progress callback  (drop-in for gui.ProgressWindow.update)
    # ------------------------------------------------------------------

    def progress_callback(self, phase, current, total, message):
        self._push_event("progress", {
            "phase": phase,
            "current": current,
            "total": total,
            "message": message,
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _push_event(self, event_type, data):
        with self._lock:
            self.events.append({"type": event_type, "data": data})

    def get_events_since(self, index):
        with self._lock:
            return self.events[index:], len(self.events)


def run_pipeline(state, max_books, full_resync=False):
    """Execute the full scrape -> Notion -> Sheets pipeline.

    Intended to run in a background :class:`threading.Thread`.
    ``full_resync=True`` rebuilds the Notion dedup cache from the live
    database before writing (restores pure-scan semantics for this run).
    """
    state.status = "running"
    state._push_event("started", {})
    store, run_id = record_run_start("web")

    try:
        main.load_config()

        with sync_playwright() as p:
            notes = main.run(
                p,
                max_books=max_books,
                progress_callback=state.progress_callback,
                two_factor_callback=state.request_two_factor,
                headless_login=True,
            )

        notion_summary = toNotion.save_notes_to_notion(
            main.NOTION_API_KEY,
            main.NOTION_DATABASE_ID,
            notes,
            progress_callback=state.progress_callback,
            force_resync=full_resync,
        )

        sheets_summary = None
        if main.GOOGLE_SHEETS_ENABLED:
            from google_sheets import toSheets

            sheets_summary = toSheets.save_notes_to_google_sheets(
                main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
                main.GOOGLE_SHEETS_SPREADSHEET_ID,
                notes,
                progress_callback=state.progress_callback,
            )

        state.status = "done"
        state._push_event("done", {"notes_count": len(notes)})
        record_run_end(
            store, run_id, status="done",
            **run_stats(notes, notion_summary, sheets_summary),
        )

    except Exception as e:
        state.status = "error"
        state._push_event("pipeline_error", {"message": str(e)})
        traceback.print_exc()
        record_run_end(
            store, run_id, status="error", error=str(e),
            scrape_mode=transformer.last_scrape_mode,
        )
