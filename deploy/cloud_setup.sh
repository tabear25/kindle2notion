#!/usr/bin/env bash
# Setup script for running kindle2notion's MANUAL-highlights path inside a
# Claude Code cloud / web environment (claude.ai/code), driven from a phone.
#
# Use it as the cloud environment's "Setup script" (point it at this file, or
# paste the body). It installs the Python deps the manual-highlights CLI needs.
# It deliberately does NOT download the Playwright browser: the manual path
# never launches one (only the Kindle scraper does), so the pip wheel is enough
# and `import main` (which imports playwright) still works.
#
# Configure these in the cloud environment first (see DOCUMENTS/MANUAL_HIGHLIGHTS.md):
#   - Environment variables:
#       NOTION_API_KEY, NOTION_DATABASE_ID,
#       GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE  (the service-account JSON, as a string),
#       GOOGLE_SHEETS_SPREADSHEET_ID,
#       NOTEBOOKLM_PARENT_FOLDER_ID         (Drive folder ID hosting the notebooklm/
#                                            50-file set; the sync writes there, since
#                                            the 01_books/02_highlights master is retired),
#       AMAZON_EMAIL, AMAZON_PASSWORD       (still required by main.load_config(),
#                                            even though the manual path is unused)
#   - Network access: "Full", or a custom allowlist that includes
#       api.notion.com   (Google Sheets' *.googleapis.com is allowed by default)
#
# Treat the env vars as semi-public: the cloud environment has no dedicated
# secret store yet, so anyone who can edit the environment can read them.
set -euo pipefail

cd "$(dirname "$0")/.."

python -m pip install --upgrade pip
python -m pip install -r requirements/requirements.txt

echo "[cloud_setup] deps installed. Manual highlights are ready, e.g.:"
echo "  python -m scripts.add_manual_highlights --list-books --title \"<タイトル>\" --matches-only"
echo "  python -m scripts.add_manual_highlights --title \"<タイトル>\" --highlight \"<本文>\"          # dry-run"
echo "  python -m scripts.add_manual_highlights --title \"<タイトル>\" --highlight \"<本文>\" --apply  # write"
