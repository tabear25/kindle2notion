import json
import os
import threading
import time

from flask import Flask, Response, jsonify, render_template, request

from web.pipeline import PipelineState, run_pipeline


def create_app():
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

    @app.route("/api/start", methods=["POST"])
    def api_start():
        nonlocal state

        if not run_lock.acquire(blocking=False):
            return jsonify({"error": "Pipeline is already running."}), 409

        try:
            body = request.get_json(silent=True) or {}
            max_books_raw = body.get("max_books")
            max_books = int(max_books_raw) if max_books_raw else None

            # Reset state for a new run
            state = PipelineState()

            worker = threading.Thread(
                target=_run_and_release,
                args=(state, max_books),
                daemon=True,
            )
            worker.start()
            return jsonify({"status": "started"})
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

    return app
