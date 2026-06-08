import json
import os
import threading
import time

from flask import Flask, Response, jsonify, render_template, request

from config import load_env_file
from scripts.add_manual_highlights import (
    DEFAULT_MATCH_CUTOFF,
    SheetsNotConfigured,
    build_books_result,
    build_notes_from_payload,
    summarize_plan,
    write_notes,
)
from web.pipeline import PipelineState, run_pipeline


def _parse_max_books(value):
    if value in (None, ""):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_books must be a positive integer.") from exc

    if parsed <= 0:
        raise ValueError("max_books must be a positive integer.")

    return parsed


def create_app():
    load_env_file()
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Shared state (single-user tool — one pipeline at a time)
    # ------------------------------------------------------------------
    state = PipelineState()
    run_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Basic HTTP auth
    # ------------------------------------------------------------------
    web_username = os.getenv("WEB_USERNAME", "")
    web_password = os.getenv("WEB_PASSWORD", "")
    auth_enabled = bool(web_username and web_password)

    @app.before_request
    def _check_auth():
        if request.path == "/healthz":
            return None
        if not auth_enabled:
            return None
        auth = request.authorization
        if auth and auth.username == web_username and auth.password == web_password:
            return None
        return Response(
            "Unauthorized",
            401,
            {"WWW-Authenticate": 'Basic realm="kindle2notion"'},
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/healthz")
    def healthz():
        """Unauthenticated health check used by Render and uptime probes."""
        return jsonify({"status": "ok"})

    @app.route("/api/start", methods=["POST"])
    def api_start():
        nonlocal state

        if not run_lock.acquire(blocking=False):
            return jsonify({"error": "Pipeline is already running."}), 409

        try:
            body = request.get_json(silent=True) or {}
            max_books = _parse_max_books(body.get("max_books"))

            # Reset state for a new run
            state = PipelineState()

            worker = threading.Thread(
                target=_run_and_release,
                args=(state, max_books),
                daemon=True,
            )
            worker.start()
            return jsonify({"status": "started"})
        except ValueError as exc:
            run_lock.release()
            return jsonify({"error": str(exc)}), 400
        except Exception:
            run_lock.release()
            raise

    def _run_and_release(pipeline_state, max_books):
        try:
            run_pipeline(pipeline_state, max_books)
        finally:
            run_lock.release()

    @app.route("/api/2fa", methods=["POST"])
    def api_two_factor():
        body = request.get_json(silent=True) or {}
        code = (body.get("code") or "").strip()
        if not code:
            return jsonify({"error": "Code is required."}), 400
        state.submit_two_factor(code)
        return jsonify({"status": "submitted"})

    @app.route("/api/events")
    def api_events():
        """Server-Sent Events stream for real-time progress."""
        def generate():
            last_index = 0
            while True:
                events, new_index = state.get_events_since(last_index)
                last_index = new_index
                for event in events:
                    payload = json.dumps(event["data"], ensure_ascii=False)
                    yield f"event: {event['type']}\ndata: {payload}\n\n"
                if state.status in ("done", "error"):
                    break
                time.sleep(0.3)

        return Response(generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    @app.route("/api/status")
    def api_status():
        """Fallback polling endpoint."""
        return jsonify({"status": state.status})

    # ------------------------------------------------------------------
    # Manual (non-Kindle) highlights — phone / assistant friendly API
    #
    # Mirrors scripts/add_manual_highlights.py so the same flow works from a
    # phone (the deployed Flask service has the Notion + Sheets credentials the
    # local CLI relies on). These endpoints are independent of the long Kindle
    # pipeline, so they do NOT take run_lock; both writers are dedup-safe.
    # ------------------------------------------------------------------

    @app.route("/api/manual/books", methods=["GET"])
    def api_manual_books():
        """Read-only: fuzzy-match a title against existing books ("この本ですか？").

        Query params: ``title`` (the user-typed title to rank against existing
        books; omit to list everything), ``cutoff`` (similarity 0..1, default
        ``DEFAULT_MATCH_CUTOFF``), ``full=1`` to also include the whole book
        list alongside the ranked matches. Returns ``sheets_configured: false``
        (HTTP 200) when Google Sheets isn't set up so the caller can fall back to
        confirming the spelling directly.
        """
        title = (request.args.get("title") or "").strip() or None

        cutoff_raw = request.args.get("cutoff")
        if cutoff_raw in (None, ""):
            cutoff = DEFAULT_MATCH_CUTOFF
        else:
            try:
                cutoff = float(cutoff_raw)
            except ValueError:
                return jsonify({"error": "cutoff must be a number between 0 and 1."}), 400
            if not (0.0 <= cutoff <= 1.0):
                return jsonify({"error": "cutoff must be between 0 and 1."}), 400

        # Default to compact output (matches only) when a title is given; pass
        # full=1 to also get the whole library.
        matches_only = request.args.get("full") not in ("1", "true", "yes", "on")

        try:
            result = build_books_result(title, match_cutoff=cutoff, matches_only=matches_only)
        except SheetsNotConfigured as exc:
            return jsonify({"sheets_configured": False, "message": str(exc)})

        result["sheets_configured"] = True
        return jsonify(result)

    @app.route("/api/manual/highlights", methods=["POST"])
    def api_manual_highlights():
        """Add manual highlights for a non-Kindle / physical book (dry-run by default).

        JSON body is the same payload the CLI accepts -- a single book
        ``{"title": ..., "highlights": [...]}`` or ``{"books": [...]}`` -- plus
        optional control keys: ``apply`` (bool, default ``false`` = dry-run),
        ``notion_only`` / ``sheets_only`` (bool, at most one). Dedup is handled
        by the writers, so re-posting the same content is safe. Always returns
        HTTP 200 with an ``ok`` flag and ``problems`` list (a partial write
        failure is ``ok: false``, not an HTTP error), so callers must check
        ``ok`` rather than the status code alone.
        """
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "Request body must be JSON."}), 400

        apply = False
        notion_only = sheets_only = False
        if isinstance(body, dict):
            apply = bool(body.get("apply", False))
            notion_only = bool(body.get("notion_only", False))
            sheets_only = bool(body.get("sheets_only", False))
            # Strip control keys so they can't leak into the payload (extra keys
            # on a book dict are ignored, but this keeps the payload clean).
            payload = {
                key: value
                for key, value in body.items()
                if key not in ("apply", "notion_only", "sheets_only")
            }
        else:
            # A bare list of books: no control keys, dry-run by default.
            payload = body

        if notion_only and sheets_only:
            return jsonify({"error": "Choose at most one of notion_only / sheets_only."}), 400

        try:
            notes = build_notes_from_payload(payload)
        except ValueError as exc:
            return jsonify({"error": f"Invalid input: {exc}"}), 400

        plan = summarize_plan(notes)
        if notion_only:
            targets = ["Notion"]
        elif sheets_only:
            targets = ["Google Sheets"]
        else:
            targets = ["Notion", "Google Sheets"]

        result = write_notes(notes, targets, apply=apply)

        return jsonify({
            "applied": apply,
            "targets": targets,
            "books": len(plan),
            "highlights": len(notes),
            "plan": [
                {"title": title, "highlights": count, "source": source}
                for title, count, source in plan
            ],
            "notion": result["notion"],
            "sheets": result["sheets"],
            "problems": result["problems"],
            "ok": not result["problems"],
        })

    return app
