"""Operational data store shared by the Turso and local SQLite backends.

This is the app's own persistence layer (introduced for the Turso migration).
It never stores highlight text — only the Playwright session blob, Notion
dedup key hashes, and run history. Notion / Google Sheets stay the actual
data destinations.

Both backends expose one primitive::

    execute(sql, args=()) -> ExecuteResult
    execute_batch([(sql, args), ...]) -> None

and ``AppStore`` builds every operation on top of it, so local runs exercise
the exact same code paths as production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class StorageError(RuntimeError):
    """Raised when a storage backend cannot complete a request."""


@dataclass
class ExecuteResult:
    rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    last_insert_rowid: int | None = None


SESSION_KEY = "playwright_storage_state"

DEDUP_INSERT_CHUNK = 100

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS app_session (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notion_dedup_key (
        database_id TEXT NOT NULL,
        key_hash    TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (database_id, key_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notion_dedup_meta (
        database_id TEXT PRIMARY KEY,
        seeded_at   TEXT NOT NULL,
        dirty       INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at            TEXT NOT NULL,
        finished_at           TEXT,
        mode                  TEXT NOT NULL,
        scrape_mode           TEXT,
        status                TEXT NOT NULL,
        books                 INTEGER,
        highlights            INTEGER,
        notion_added          INTEGER,
        notion_skipped        INTEGER,
        notion_failed         INTEGER,
        sheets_new_highlights INTEGER,
        error                 TEXT
    )
    """,
]

RUN_END_FIELDS = (
    "status",
    "scrape_mode",
    "books",
    "highlights",
    "notion_added",
    "notion_skipped",
    "notion_failed",
    "sheets_new_highlights",
    "error",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AppStore:
    """Backend-agnostic operations for session / dedup cache / run history."""

    def __init__(self, backend, supports_session: bool):
        self._backend = backend
        # Local mode keeps the Playwright session file-only (today's
        # behavior); only Turso mirrors it so it survives PaaS restarts.
        self.supports_session = supports_session

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__

    def execute(self, sql: str, args=()) -> ExecuteResult:
        return self._backend.execute(sql, args)

    def ensure_schema(self) -> None:
        self._backend.execute_batch([(sql, ()) for sql in SCHEMA_STATEMENTS])

    # ------------------------------------------------------------------
    # Playwright session blob
    # ------------------------------------------------------------------

    def load_session(self):
        """Return ``(value, updated_at)`` or ``None`` when unavailable."""
        if not self.supports_session:
            return None
        result = self.execute(
            "SELECT value, updated_at FROM app_session WHERE key = ?",
            (SESSION_KEY,),
        )
        if not result.rows:
            return None
        value, updated_at = result.rows[0][0], result.rows[0][1]
        return (value, updated_at)

    def save_session(self, value: str) -> None:
        if not self.supports_session:
            return
        self.execute(
            "INSERT INTO app_session (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (SESSION_KEY, value, now_iso()),
        )

    # ------------------------------------------------------------------
    # Notion dedup key cache
    # ------------------------------------------------------------------

    def is_seeded(self, database_id: str) -> bool:
        """True when the cache was seeded and is not marked dirty."""
        result = self.execute(
            "SELECT dirty FROM notion_dedup_meta WHERE database_id = ?",
            (database_id,),
        )
        if not result.rows:
            return False
        return int(result.rows[0][0] or 0) == 0

    def get_dedup_hashes(self, database_id: str) -> set:
        result = self.execute(
            "SELECT key_hash FROM notion_dedup_key WHERE database_id = ?",
            (database_id,),
        )
        return {row[0] for row in result.rows}

    def seed_dedup_hashes(self, database_id: str, hashes) -> None:
        """Replace the cached key set for ``database_id`` and clear dirty."""
        self.execute(
            "DELETE FROM notion_dedup_key WHERE database_id = ?",
            (database_id,),
        )
        self.append_dedup_hashes(database_id, hashes)
        self.execute(
            "INSERT INTO notion_dedup_meta (database_id, seeded_at, dirty) "
            "VALUES (?, ?, 0) "
            "ON CONFLICT(database_id) DO UPDATE SET seeded_at = excluded.seeded_at, "
            "dirty = 0",
            (database_id, now_iso()),
        )

    def append_dedup_hashes(self, database_id: str, hashes) -> None:
        hashes = list(hashes)
        if not hashes:
            return
        created_at = now_iso()
        statements = [
            (
                "INSERT OR IGNORE INTO notion_dedup_key "
                "(database_id, key_hash, created_at) VALUES (?, ?, ?)",
                (database_id, key_hash, created_at),
            )
            for key_hash in hashes
        ]
        for start in range(0, len(statements), DEDUP_INSERT_CHUNK):
            self._backend.execute_batch(statements[start:start + DEDUP_INSERT_CHUNK])

    def mark_dirty(self, database_id: str) -> None:
        """Flag the cache as suspect so the next load reseeds from Notion."""
        self.execute(
            "INSERT INTO notion_dedup_meta (database_id, seeded_at, dirty) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(database_id) DO UPDATE SET dirty = 1",
            (database_id, now_iso()),
        )

    def clear_dedup(self, database_id: str) -> None:
        self.execute(
            "DELETE FROM notion_dedup_key WHERE database_id = ?",
            (database_id,),
        )
        self.execute(
            "DELETE FROM notion_dedup_meta WHERE database_id = ?",
            (database_id,),
        )

    # ------------------------------------------------------------------
    # Run history
    # ------------------------------------------------------------------

    def record_run_start(self, mode: str):
        result = self.execute(
            "INSERT INTO run_history (started_at, mode, status) "
            "VALUES (?, ?, 'running')",
            (now_iso(), mode),
        )
        return result.last_insert_rowid

    def record_run_end(self, run_id, **fields) -> None:
        if run_id is None:
            return
        unknown = set(fields) - set(RUN_END_FIELDS)
        if unknown:
            raise ValueError(f"Unknown run_history fields: {sorted(unknown)}")
        assignments = ["finished_at = ?"]
        args: list = [now_iso()]
        for name in RUN_END_FIELDS:
            if name in fields:
                assignments.append(f"{name} = ?")
                args.append(fields[name])
        args.append(run_id)
        self.execute(
            f"UPDATE run_history SET {', '.join(assignments)} WHERE id = ?",
            tuple(args),
        )

    def list_runs(self, limit: int = 20) -> list:
        result = self.execute(
            "SELECT * FROM run_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(zip(result.columns, row)) for row in result.rows]
