"""Persist the Playwright storage_state across runs.

The local file (``STORAGE_STATE_PATH``) stays the working copy that Playwright
reads; when the store supports sessions (Turso), the blob is mirrored there so
it survives PaaS restarts and redeploys. Hydration is newer-wins so a fresh
local login is never clobbered by a stale remote blob.

Storage failures are never fatal here — worst case the app falls back to
today's behavior (a fresh Amazon login).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_RETRY_WAIT_SECONDS = 3


def _parse_iso(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _file_mtime(path: Path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def hydrate_session_file(store, path) -> bool:
    """Pull the stored session blob into ``path`` if it is newer than the file.

    Returns True when a session file exists afterwards.
    """
    path = Path(path)
    if store is None or not store.supports_session:
        return path.exists()

    try:
        row = store.load_session()
    except Exception as exc:
        print(f"Warning: could not read session from the store: {exc}")
        return path.exists()

    if row is None:
        return path.exists()

    value, updated_at = row
    stored_at = _parse_iso(updated_at)
    file_at = _file_mtime(path)
    if file_at is not None and (stored_at is None or stored_at <= file_at):
        return True

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not write session file {path}: {exc}")
        return path.exists()
    return True


def persist_session_file(context, store, path) -> None:
    """Save ``context.storage_state`` to ``path`` and mirror it to the store.

    Snapshotting is best-effort: ``context.storage_state()`` can time out
    while a heavy page (e.g. the freshly logged-in Amazon notebook) is still
    executing scripts. Persistence being a convenience, a failed snapshot
    must never abort the sync — retry once after a settle, then skip with a
    warning (the next persist point or run will try again).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        context.storage_state(path=str(path))
    except Exception as exc:
        print(f"Warning: session snapshot failed ({exc}); retrying once...")
        time.sleep(SNAPSHOT_RETRY_WAIT_SECONDS)
        try:
            context.storage_state(path=str(path))
        except Exception as retry_exc:
            print(
                "Warning: session snapshot failed again "
                f"({retry_exc}); continuing without saving the session."
            )
            return

    if store is None or not store.supports_session:
        return
    try:
        store.save_session(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: could not mirror session to the store: {exc}")
