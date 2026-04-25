# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Setup:

```bash
pip install -r requirements/requirements.txt
playwright install chromium
```

Run the tool:

```bash
python main.py        # Tkinter GUI
python web_main.py    # Flask web UI on 0.0.0.0:5000 (override with WEB_HOST / WEB_PORT)
```

Verification commands the README treats as authoritative:

```bash
python -m compileall .
python -m pytest test -q -p no:cacheprovider
```

Note: the `test/` directory is `.gitignore`-d, so freshly cloned repos will collect 0 tests. Tests are expected to live locally only — do not assume they exist when running pytest in CI/sandbox.

Deploy: pushing to `main` triggers `.github/workflows/deploy.yml`, which SSHes into the VPS and runs `git reset --hard origin/main` + `pip install -r requirements/requirements.txt` + `systemctl restart kindle2notion-web.service`. `main` is effectively the production branch.

## Architecture

### Two front-ends, one pipeline

`main.py` (Tkinter GUI) and `web_main.py` → `web/app.py` (Flask) both drive the same scrape → Notion (→ optional Google Sheets) pipeline. The web flow re-uses `main` as a library:

- `web/pipeline.py` calls `main.load_config()` then reads `main.NOTION_API_KEY`, `main.GOOGLE_SHEETS_*`, etc. as module-level globals.
- `main.run(playwright, ...)` is the actual scrape entry point used by both front-ends.

When changing `main.py`'s config loading or its module-level globals, update `web/pipeline.py` in lockstep — the web pipeline depends on the names of those globals, not on a return value.

### Config loading is a one-shot singleton

`config/__init__.py` exposes `BASE_DIR` and `load_env_file()`. `main.load_config()` wraps it with a `_config_loaded` flag, validates required vars, and decides `GOOGLE_SHEETS_ENABLED` (true only if both `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` and `GOOGLE_SHEETS_SPREADSHEET_ID` are set; partial config raises). `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` accepts either a path or inline JSON — detected by leading `{`.

`config/KEYS.env` is the only env source and is gitignored. There is no support for OS-level env vars overriding it unless `load_env_file(override=True)` is used.

### 2FA bridge between threads

`amazon/login.py:perform_login` accepts a `two_factor_callback` that blocks until a code is returned:

- GUI: callback opens a Tk dialog (`gui_utils.gui.prompt_two_factor_code`).
- Web: `web/pipeline.py:PipelineState.request_two_factor` flips state to `waiting_2fa`, pushes a `2fa_required` SSE event, and `wait()`s on a `threading.Event` for up to 5 minutes. `/api/2fa` calls `submit_two_factor` to release it.

The web pipeline always launches Playwright with `headless_login=True`; the GUI uses `headless=False` so the login window is visible (and `allow_manual_auth=True`, so the user can complete extra Amazon checks in the browser).

### Dedup key is shared across sinks

`note_utils.build_note_key(title, content, page)` produces the canonical `(title, content, page)` tuple used by both `notion/toNotion.py:get_existing_note_keys` and `google_sheets/toSheets.py:_get_existing_note_keys`. If the dedup contract changes, both sinks must change together. Notion property names `Title` / `Content` / `Page` are hardcoded in `notion/toNotion.py`; the README documents this and tells users to rename in code if they rename the DB.

Google Sheets additionally skips notes with empty `content` (`note_key[1]`) — Notion does not.

### Web app concurrency model

`web/app.py:create_app` keeps everything in-process:

- A module-level `run_lock = threading.Lock()` enforces one pipeline at a time; `/api/start` returns 409 if a run is already active.
- `PipelineState` is recreated per run and held by closure. Restarting the server wipes all state.
- `/api/events` is SSE; `/api/status` is a polling fallback. SSE breaks out of its loop only when status is `done` or `error`.
- Basic auth is enabled iff both `WEB_USERNAME` and `WEB_PASSWORD` are set. **External deployments must set these** — unauthenticated public exposure is the documented anti-pattern in the README.

### Why `nest_asyncio.apply()` in main.py

Required so Playwright's sync API works when called from inside Flask request-spawned threads (which already have an event loop). Don't remove it.

## Files that are intentionally not in git

`.gitignore` excludes `KEYS.env`, `config/KEYS.env`, `*.json` (including `storage_state.json` Playwright session and any service account JSONs), `/test`, and `CLAUDE/`. Don't try to commit these or add them as fixtures.
