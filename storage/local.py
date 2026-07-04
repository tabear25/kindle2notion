"""Local SQLite backend (stdlib ``sqlite3``) for the operational store.

Used automatically when ``TURSO_DATABASE_URL`` / ``TURSO_AUTH_TOKEN`` are not
set, so local GUI runs and tests exercise the same ``AppStore`` code paths as
production. A fresh connection is opened per call: the Flask request threads
and the pipeline worker thread all hit the store, and ``sqlite3`` connections
must not cross threads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from storage.base import ExecuteResult, StorageError


class SqliteBackend:
    def __init__(self, db_path):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def execute(self, sql: str, args=()) -> ExecuteResult:
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(sql, tuple(args))
                rows = [list(row) for row in cursor.fetchall()]
                columns = (
                    [col[0] for col in cursor.description]
                    if cursor.description
                    else []
                )
                return ExecuteResult(
                    rows=rows,
                    columns=columns,
                    last_insert_rowid=cursor.lastrowid,
                )
        except sqlite3.Error as exc:
            raise StorageError(f"SQLite error: {exc}") from exc

    def execute_batch(self, statements) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                for sql, args in statements:
                    conn.execute(sql, tuple(args))
        except sqlite3.Error as exc:
            raise StorageError(f"SQLite error: {exc}") from exc
