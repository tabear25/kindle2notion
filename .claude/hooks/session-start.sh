#!/bin/bash
# SessionStart hook: install Python dependencies so kindle2notion scripts
# (especially scripts/add_manual_highlights.py) work in Claude Code on the web.
#
# Runs only in the remote (web) environment, where the container is created
# fresh each session. Idempotent: if the key modules already import, it skips
# the (slow) pip install so cached containers start fast.
set -euo pipefail

# Web sessions only; local machines manage their own venv.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Fast path: deps already present (cached container) -> nothing to do.
if python -c "import nest_asyncio, playwright, notion_client, gspread, google.auth, dotenv, flask" 2>/dev/null; then
  echo "[session-start] dependencies already installed; skipping pip install"
  exit 0
fi

echo "[session-start] installing Python dependencies from requirements/requirements.txt ..."
# --ignore-installed sidesteps a Debian-managed blinker that pip cannot uninstall.
python -m pip install -q --ignore-installed blinker -r requirements/requirements.txt

echo "[session-start] done."
