"""Minimal CORS support for the cross-origin frontend (no new dependency).

Only origins listed in ``CORS_ALLOWED_ORIGINS`` (comma-separated, exact
match — e.g. ``https://kindle2notion.vercel.app``) receive CORS headers.
When the variable is unset nothing is added at all, which is today's
same-origin-only behavior.

The wildcard ``*`` is deliberately not supported: the API sits behind Basic
auth and must only be scriptable from the deployed frontend.
"""

from __future__ import annotations

import os

from flask import request

ALLOWED_ORIGINS_ENV = "CORS_ALLOWED_ORIGINS"
ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Authorization, Content-Type"
MAX_AGE_SECONDS = "86400"


def allowed_origins() -> set:
    raw = os.getenv(ALLOWED_ORIGINS_ENV) or ""
    return {origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()}


def init_cors(app) -> None:
    allowed = allowed_origins()
    if not allowed:
        return

    def _origin_if_allowed():
        origin = (request.headers.get("Origin") or "").rstrip("/")
        return origin if origin in allowed else None

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
        origin = _origin_if_allowed()
        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.vary.add("Origin")  # HeaderSet dedupes repeated adds
        return response
