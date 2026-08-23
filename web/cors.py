"""Minimal CORS support for the cross-origin frontend (no new dependency).

Only origins listed in ``CORS_ALLOWED_ORIGINS`` (comma-separated, exact
match — e.g. ``https://kindle2notion.vercel.app``) receive CORS headers.
When the variable is unset nothing is added for the API routes, which is
today's same-origin-only behavior.

The wildcard ``*`` is deliberately not supported *for the API*: it sits
behind Basic auth and must only be scriptable from the deployed frontend.

``/healthz`` is the one exception and always answers ``*``. It is already
unauthenticated (see ``web/app.py``) and returns a constant body, so it
leaks nothing — and making it universally readable turns it into a
trustworthy liveness probe for the frontend. That matters because Render's
router serves its own 502/503 pages while an instance boots, and those
carry no CORS headers: a readable ``/healthz`` therefore proves the Flask
app itself answered, not the edge in front of it.
"""

from __future__ import annotations

import os

from flask import request

ALLOWED_ORIGINS_ENV = "CORS_ALLOWED_ORIGINS"
ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Authorization, Content-Type"
MAX_AGE_SECONDS = "86400"
# Unauthenticated, constant-body route: always CORS-readable (see module docstring).
HEALTH_PATH = "/healthz"


def allowed_origins() -> set:
    raw = os.getenv(ALLOWED_ORIGINS_ENV) or ""
    return {origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()}


def init_cors(app) -> None:
    allowed = allowed_origins()

    def _origin_if_allowed():
        origin = (request.headers.get("Origin") or "").rstrip("/")
        return origin if origin in allowed else None

    if allowed:

        @app.before_request
        def _cors_preflight():
            if request.method != "OPTIONS":
                return None
            origin = _origin_if_allowed()
            if origin is None:
                return None
            response = app.make_default_options_response()
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
            response.headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
            response.headers["Access-Control-Max-Age"] = MAX_AGE_SECONDS
            response.vary.add("Origin")
            return response

    @app.after_request
    def _cors_headers(response):
        # Registered even with no allowlist, because /healthz must stay
        # readable everywhere. A plain GET with no custom headers is a simple
        # request, so this needs no preflight and no Vary: the answer is the
        # same for every origin.
        if request.path == HEALTH_PATH:
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
        if not allowed:
            return response
        origin = _origin_if_allowed()
        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.vary.add("Origin")  # HeaderSet dedupes repeated adds
        return response
