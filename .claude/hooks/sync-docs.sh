#!/usr/bin/env bash
# Stop hook: ask a child `claude` to sync CLAUDE.md / README.md after each turn.
#
# Loop-prevention contract (must NOT be removed):
#   - The child claude is launched with KINDLE2NOTION_SYNC_DOCS=1 in its env.
#   - Its own Stop hook re-runs THIS script, which exits 0 immediately when
#     that variable is set. Without this guard, every doc-sync would trigger
#     another doc-sync forever.
set -euo pipefail

if [ "${KINDLE2NOTION_SYNC_DOCS:-}" = "1" ]; then
  exit 0
fi

LOCK="/tmp/kindle2notion-sync-docs.lock"
if [ -e "$LOCK" ]; then
  exit 0
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$PROJECT_DIR" ] || ! cd "$PROJECT_DIR" 2>/dev/null; then
  exit 0
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi
if ! git log -1 >/dev/null 2>&1; then
  exit 0
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

HAS_LOCAL_COMMITS=0
if git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
  if [ -n "$(git rev-list "origin/$BRANCH..HEAD" 2>/dev/null)" ]; then
    HAS_LOCAL_COMMITS=1
  fi
fi
HAS_WORKTREE_CHANGES=0
if [ -n "$(git status --porcelain)" ]; then
  HAS_WORKTREE_CHANGES=1
fi

# Always run if there's anything new since the last upstream state. If both are
# clean (no local commits, no working-tree changes) there's nothing the child
# could meaningfully sync, so skip and save tokens.
if [ "$HAS_LOCAL_COMMITS" = "0" ] && [ "$HAS_WORKTREE_CHANGES" = "0" ]; then
  exit 0
fi

LOG_DIR="$PROJECT_DIR/.claude"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync-docs.log"
{
  echo "===== $(date -Iseconds) sync-docs start (branch=$BRANCH) ====="
} >> "$LOG"

PROMPT='Project: kindle2notion. You are running inside a Stop hook to keep CLAUDE.md and README.md aligned with the most recent code changes. The user is not present — work autonomously and finish in a single turn.

Do exactly this:

1. Inspect what changed in this turn:
   - `git rev-parse --abbrev-ref HEAD` to find the branch.
   - `git log --oneline -5` for recent commits.
   - If `origin/<branch>` exists, run `git diff origin/<branch>..HEAD` and `git status --porcelain`. Otherwise run `git diff HEAD~1..HEAD` and `git status --porcelain`.

2. Read the current CLAUDE.md and README.md.

3. Decide whether either doc is now stale because the diff:
   - added/removed/renamed a command, env var, file path, module, or public function
   - changed a cross-file architectural contract documented in CLAUDE.md
   - changed user-facing setup or run instructions documented in README.md.
   If nothing in the diff invalidates the docs, do nothing and exit without committing.

4. If updates are required:
   - Make the smallest possible edits — fix only stale facts. Do not restructure, do not rephrase unaffected sections, do not add new sections unless the change introduced a genuinely new concept.
   - `git add CLAUDE.md README.md` (only those two files).
   - Commit with a one-line message of the form `docs: sync CLAUDE.md/README.md after <short summary of triggering change>`.
   - `git push -u origin <current-branch>`. If push fails for network reasons, retry up to 3 times with 2s/4s/8s backoff, then give up silently.

Hard constraints:
- Touch ONLY CLAUDE.md and README.md. Never edit, create, or delete any other file.
- Do not run tests, linters, formatters, build commands, or anything not listed above.
- Do not amend prior commits. Do not force-push. Do not rebase.
- Do not open a pull request.
- If you are unsure whether an update is warranted, prefer doing nothing.'

KINDLE2NOTION_SYNC_DOCS=1 claude \
  -p \
  --permission-mode bypassPermissions \
  "$PROMPT" \
  </dev/null >>"$LOG" 2>&1 || true

{
  echo "===== $(date -Iseconds) sync-docs end ====="
} >> "$LOG"
