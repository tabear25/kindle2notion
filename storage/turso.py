"""Turso backend speaking the libsql HTTP v2 pipeline protocol.

Implemented directly over ``requests`` on purpose: the official libsql Python
clients ship native extensions with patchy Windows wheel coverage, while this
project is developed on Windows and deployed on Linux. The protocol itself is
a single JSON POST per call:

    POST {https_url}/v2/pipeline
    Authorization: Bearer {token}
    {"requests": [{"type": "execute", "stmt": {...}}, {"type": "close"}]}
"""

from __future__ import annotations

import time

import requests

from storage.base import ExecuteResult, StorageError

REQUEST_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 0.5


def _http_url(database_url: str) -> str:
    url = (database_url or "").strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    if not url.startswith("https://") and not url.startswith("http://"):
        raise StorageError(f"Unsupported Turso URL: {database_url!r}")
    return url


def _encode_arg(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def _decode_cell(cell):
    cell_type = cell.get("type")
    if cell_type == "null":
        return None
    if cell_type == "integer":
        return int(cell.get("value"))
    if cell_type == "float":
        return float(cell.get("value"))
    return cell.get("value")


class TursoBackend:
    def __init__(self, database_url: str, auth_token: str):
        self._pipeline_url = _http_url(database_url) + "/v2/pipeline"
        self._headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------

    def execute(self, sql: str, args=()) -> ExecuteResult:
        results = self._pipeline([(sql, args)])
        return results[0]

    def execute_batch(self, statements) -> None:
        statements = list(statements)
        if statements:
            self._pipeline(statements)

    # ------------------------------------------------------------------

    def _pipeline(self, statements) -> list:
        payload = {
            "requests": [
                {"type": "execute", "stmt": self._stmt(sql, args)}
                for sql, args in statements
            ]
            + [{"type": "close"}]
        }
        body = self._post(payload)

        execute_results = []
        for entry in body.get("results", [])[: len(statements)]:
            if entry.get("type") == "error":
                message = entry.get("error", {}).get("message", "unknown error")
                raise StorageError(f"Turso statement failed: {message}")
            execute_results.append(self._decode_result(entry))
        return execute_results

    @staticmethod
    def _stmt(sql: str, args) -> dict:
        return {"sql": sql, "args": [_encode_arg(value) for value in args]}

    def _post(self, payload: dict) -> dict:
        last_error = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = requests.post(
                    self._pipeline_url,
                    json=payload,
                    headers=self._headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last_error = StorageError(f"Turso request failed: {exc}")
            else:
                if response.status_code < 500:
                    if response.status_code >= 400:
                        raise StorageError(
                            f"Turso HTTP {response.status_code}: {response.text[:200]}"
                        )
                    return response.json()
                last_error = StorageError(
                    f"Turso HTTP {response.status_code}: {response.text[:200]}"
                )
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(RETRY_WAIT_SECONDS * (attempt + 1))
        raise last_error

    @staticmethod
    def _decode_result(entry: dict) -> ExecuteResult:
        result = entry.get("response", {}).get("result", {})
        columns = [col.get("name") for col in result.get("cols", [])]
        rows = [
            [_decode_cell(cell) for cell in row]
            for row in result.get("rows", [])
        ]
        last_insert_rowid = result.get("last_insert_rowid")
        if last_insert_rowid is not None:
            last_insert_rowid = int(last_insert_rowid)
        return ExecuteResult(
            rows=rows,
            columns=columns,
            last_insert_rowid=last_insert_rowid,
        )
