"""Factory for the app's operational store (Turso in prod, SQLite locally).

Selection:
- ``TURSO_DATABASE_URL`` + ``TURSO_AUTH_TOKEN`` set -> Turso over HTTP.
- otherwise -> local SQLite file at ``K2N_LOCAL_DB_PATH``
  (default ``<project>/local_store.db``).

``get_store()`` memoizes a single instance and creates the schema on first
use. Callers are expected to wrap store usage in try/except and degrade
gracefully (session -> local file, dedup -> full Notion scan, history ->
skip); a broken store must never fail a sync run.
"""

from __future__ import annotations

import os
from pathlib import Path

from config import BASE_DIR
from storage.base import AppStore, StorageError  # noqa: F401  (re-exported)
from storage.local import SqliteBackend
from storage.turso import TursoBackend

_store: AppStore | None = None


def get_store() -> AppStore:
    global _store
    if _store is None:
        store = _build_store()
        store.ensure_schema()
        _store = store
    return _store


def reset_store_for_tests() -> None:
    global _store
    _store = None


def _build_store() -> AppStore:
    turso_url = (os.getenv("TURSO_DATABASE_URL") or "").strip()
    turso_token = (os.getenv("TURSO_AUTH_TOKEN") or "").strip()
    if turso_url and turso_token:
        return AppStore(
            TursoBackend(turso_url, turso_token),
            supports_session=True,
        )

    db_path = (os.getenv("K2N_LOCAL_DB_PATH") or "").strip()
    if not db_path:
        db_path = str(Path(BASE_DIR) / "local_store.db")
    return AppStore(SqliteBackend(db_path), supports_session=False)
