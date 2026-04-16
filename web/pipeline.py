import json
import threading
import traceback

from playwright.sync_api import sync_playwright

import main
from notion import toNotion


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

    def request_two_factor(self):
        """Called from the Playwright thread.  Blocks until a code arrives."""
        self.status = "waiting_2fa"
        self._push_event("2fa_required", {})
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


def run_pipeline(state, max_books):
    """Execute the full scrape -> Notion -> Sheets pipeline.

    Intended to run in a background :class:`threading.Thread`.
    """
    state.status = "running"
    state._push_event("started", {})

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

        toNotion.save_notes_to_notion(
            main.NOTION_API_KEY,
            main.NOTION_DATABASE_ID,
            notes,
            progress_callback=state.progress_callback,
        )

        if main.GOOGLE_SHEETS_ENABLED:
            from google_sheets import toSheets

            toSheets.save_notes_to_google_sheets(
                main.GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE,
                main.GOOGLE_SHEETS_SPREADSHEET_ID,
                main.GOOGLE_SHEETS_WORKSHEET_NAME,
                notes,
                progress_callback=state.progress_callback,
            )

        state.status = "done"
        state._push_event("done", {"notes_count": len(notes)})

    except Exception as e:
        state.status = "error"
        state._push_event("error", {"message": str(e)})
        traceback.print_exc()
