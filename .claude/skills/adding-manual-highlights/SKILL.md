---
name: adding-manual-highlights
description: >-
  Add highlights for books that the Kindle scraper cannot reach -- paper / physical
  books, library loans, PDFs, or e-books from non-Kindle stores -- into the same
  Notion database and Google Sheets that kindle2notion already uses. Trigger when
  the user wants to add or record highlights / quotes / 抜き書き for a book by hand,
  e.g. "この本のハイライト追加して", "紙の本のメモを登録したい", "Kindleにない本の
  引用を入れて", "add highlights for <book>". Do NOT use for the normal Kindle sync
  (that is `python main.py`); this is only for manually supplied highlights.
---

# Adding manual (non-Kindle) highlights

The user reads books that are not on Amazon Kindle (paper books, PDFs, library
loans, other e-book stores). Their highlights cannot be scraped, so collect them
in conversation and write them into the **same** Notion database + the same
NotebookLM Google Sheets layout the Kindle sync uses. The output is
indistinguishable from scraped highlights. The write goes **straight into the 100
NotebookLM files** (`split_per_book.sync_notes_to_notebooklm`) — there is no
separate "run the split" step anymore (see Step 6).

Always converse with the user in **Japanese** (this is a Japanese user).

## Three execution modes — pick one up front

The same logic is reachable three ways. The data-gathering (Step 1), the typo
guard (Step 2), and dry-run-then-confirm-then-apply are **identical** in all of
them; only *how you invoke it* differs. Pick by where you are running:

- **Local CLI** — on the user's PC with this repo and the `py` launcher. Run
  `py -m scripts.add_manual_highlights ...` (Steps 1–6 below). Use whenever you
  can. Check with `py -m scripts.add_manual_highlights --help`.
- **Cloud Claude Code (run the CLI in the cloud)** — you are in a
  claude.ai/code cloud session connected to **this GitHub repo**, with the
  required env vars set in the cloud environment and `deploy/cloud_setup.sh`
  having installed the deps. This is the lightest "from a phone" path: the
  **same CLI**, just `python` instead of `py`, and no deployed server needed.
  See **"Cloud mode"** below. Check with `python -m scripts.add_manual_highlights --help`.
- **Deployed HTTP API (curl from anywhere)** — you cannot run the script at all
  (no repo / no env), but the user runs this tool as a deployed web service
  (`deploy/README.md`) that holds the same credentials. Drive it over HTTP with
  `curl`. See **"HTTP API mode"** below.

If both a cloud session *and* a deployed service are available, prefer the
**cloud CLI** (no dependency on the server being awake). Use the **HTTP API**
when you can't run the script (e.g. a non-Claude-Code surface, or no GitHub
connection) but the service is up.

## Step 1 — Gather the book and highlights

Ask the user for the information below. Ask only for what is missing; if they
already pasted highlights, parse those instead of re-asking. Keep it to one or
two questions — don't interrogate.

Required:
- **本のタイトル** (`title`) — exactly as they want it stored. ⚠️ A manual book
  merges with an existing book **only if the title matches character-for-character**
  (the `book_id` is derived from the raw title). A typo therefore silently creates
  a *separate* book. Step 2 below reconciles the typed title against existing books
  before writing — do not skip it.
- **ハイライト本文** (`content`) — one or more. A page number (`page`) or Kindle
  location (`location`) per highlight is optional but nice to have.

Optional book metadata — ⚠️ **currently NOT persisted anywhere**. These fields
(`author` 著者 / `genre` / `reading_status` / `finished_at` / `rating` /
`amazon_asin` / `cover_url` / `notion_url`) and the `source` label used to live on
the retired `01_books` master; the NotebookLM 100-file layout has no columns for
them and Notion stores only Title/Content/Page. The payload still *accepts* them
(harmless), but they will not be saved. So don't go out of your way to collect
metadata — focus on the title + highlights (+ optional page/location). Mention to
the user that metadata isn't stored if they offer it.

## Step 2 — Reconcile the title against existing books (typo guard)

Because `book_id` is derived from the title, a small typo / spacing / 表記ゆれ
（全角半角・かな漢字・「&」と「アンド」など）creates a duplicate book instead of
merging. Before writing, check the title the user gave against the books already
on record:

```bash
py -m scripts.add_manual_highlights --list-books --matches-only --title "<ユーザーが言ったタイトル>"
```

This is **read-only** (it never writes). `--matches-only` keeps the output compact
(just the ranked matches, not the whole library). It prints JSON:

```json
{
  "count": 123,
  "query_title": "ファストアンドスロー",
  "matches_for_title": [
    {"title": "ファスト&スロー", "score": 0.83, "book_id": "BK-AB12CD", "is_exact_normalized": false}
  ]
}
```

> If Google Sheets is **not configured**, this command exits with a message
> (it reads the NotebookLM index file). In that case skip the reconcile and just
> confirm the title spelling directly with the user before continuing.

How to act on it:
- **`is_exact_normalized: true`** (score 1.0) — same book modulo full/half-width
  or spacing. Use that existing `title` verbatim; no need to ask.
- **A close match** (high score, or your own judgement says it's the same book —
  you are better than the score at kana/kanji and word-order variants) — ask the
  user in Japanese: 「もしかして既存の『ファスト&スロー』のことですか？ そちらに
  追記しますか？」 If yes, use the existing title verbatim.
- **No good match** — treat it as a genuinely new book and use the user's title
  as given.

Use your own reasoning in addition to `score`: the difflib score is a safety net,
not the decision (it is weak for kana↔kanji reading variants — your judgement is
better). If `matches_for_title` is empty but you still suspect a match, drop
`--matches-only` to get the full `books` list and scan it yourself.
`--match-cutoff 0.5` widens the net if needed.

Only proceed once the **canonical title is settled** — that exact string is what
you put in the payload below.

## Step 3 — Build the JSON payload

Write the collected data to a temporary JSON file with the **Write** tool. Use a
`.json` name inside the project (e.g. `manual_highlights_input.json` in the repo
root) — `*.json` is already git-ignored, so it will not be committed.

```json
{
  "books": [
    {
      "title": "ファスト&スロー",
      "author": "ダニエル・カーネマン",
      "reading_status": "読了",
      "finished_at": "2026-05-30",
      "source": "physical",
      "highlights": [
        {"content": "システム1は速く、システム2は遅い。", "page": "42"},
        {"content": "利用可能性ヒューリスティック。", "page": "120"}
      ]
    }
  ]
}
```

Notes:
- The `title` must be the canonical title settled in Step 2.
- For a single book you may also write just `{ "title": ..., "highlights": [...] }`
  without the `books` wrapper.
- A highlight can be a bare string (`"本文だけ"`) when there is no page/location.
- Put a physical book's page number in `page`; it appears in Notion's *Page*
  property. In the NotebookLM volume file, a page-only highlight is stored in the
  **`location`** column (volume rows carry `location`, falling back to `page`), so
  the value is never lost and manual + scraped highlights stay consistent.

## Step 4 — Dry-run and confirm (do not skip)

Writing to Notion / Sheets is an external write, so always preview first:

```bash
py -m scripts.add_manual_highlights --input manual_highlights_input.json
```

Show the user the `[plan]` output **in Japanese** (何冊・何ハイライトを、どこに
追加するか）and ask for confirmation before writing. Dedup is automatic, so
re-adding the same highlight is safe; still confirm.

## Step 5 — Apply

After the user confirms:

```bash
py -m scripts.add_manual_highlights --input manual_highlights_input.json --apply
```

Report the result in Japanese using the script's summary lines:
- `[Notion] added N, skipped M (already present), failed K`
- `[Google Sheets] new books B, new highlights H, skipped M (already present), dropped D (empty title/content)`

**Do not report a partial failure as success.** If `failed K` (Notion) is > 0 or
`dropped D` (Sheets) is > 0, the script also prints a `[partial failure] ...`
line and exits non-zero. In that case, tell the user **in Japanese** exactly what
did not get written and offer to retry, rather than just saying「追加しました」。

If Google Sheets is not configured, the script prints that it skipped Sheets and
only Notion is updated — relay that to the user.

Optional flags: `--notion-only` / `--sheets-only` to target one destination.

## Step 6 — (No manual split needed — propagation is automatic)

**This step no longer requires any action.** `add_manual_highlights --apply`
writes **directly** into the 100 NotebookLM files via
`split_per_book.sync_notes_to_notebooklm`: the new highlights land in their
pinned volume(s) and the index is refreshed in the **same run** as Step 5. There
is no separate `split_per_book --apply` to run, and there is no `01_books` /
`02_highlights` master in the loop anymore.

What this means in practice:
- The Step 5 `[Google Sheets] ...` summary already reflects what was written to
  the NotebookLM files. If Google Sheets is not configured, only Notion is
  updated (relay that).
- **Folder location**: the user must have `NOTEBOOKLM_PARENT_FOLDER_ID` set in
  `config/KEYS.env` — the Drive folder ID that **holds the 100 files** (or a parent
  containing a `notebooklm/` subfolder; both work) so the sync can find them. If
  it's unset and the fallback can't resolve the folder, the run errors — relay
  that and ask the user to set it.
- **Missing files**: the service account cannot create Drive files. If a needed
  volume file (or the index) doesn't exist yet, the run reports it as a partial
  failure (`[partial failure] ... NotebookLM ... file(s) missing`) and those
  highlights are NOT written. Tell the user which file names to create once (as
  empty Google Sheets with those exact names), then re-run.
- `py -m scripts.split_per_book --apply` still exists but now only **rebuilds the
  index from the volumes** (a safe recovery tool). You normally never need it.
  Never use `--from-master` here — it overwrites all 100 files from the retired
  master and would clobber recent highlights.

## Step 7 — Clean up

Delete the temporary `*.json` input file after a successful run (it is
git-ignored but leaving it around is untidy). Confirm to the user what was added.

## Notes / gotchas

- The Python launcher on this machine is `py` (not `python`). Run scripts as
  `py -m scripts.add_manual_highlights ...` from the project root.
- Book metadata (`author`, `genre`, `rating`, …) and the `source` label are **not
  persisted** in the current model — they only ever lived on the retired
  `01_books`. Notion stores only Title / Content / Page, and the NotebookLM
  files have no metadata/source columns. Don't promise the user these are saved.
- This never runs the Kindle scraper and never touches `storage_state.json`.
- `NOTEBOOKLM_PARENT_FOLDER_ID` must point at the live Drive folder that **holds
  the 100 files** (or a parent with a `notebooklm/` subfolder — both work). The
  retired master spreadsheet should NOT be relied on for folder resolution (it
  may be trashed).

## Cloud mode — run the CLI inside a cloud Claude Code session

Use this when you are in a **claude.ai/code cloud session** connected to this
repo (typical "from my phone" case). It is just **Local mode with `python`**, so
Steps 1–7 above apply verbatim — only the launcher changes (`py` → `python`).
The `--apply` in Step 5 writes straight into the 100 NotebookLM files (no separate
split step — see Step 6); set `NOTEBOOKLM_PARENT_FOLDER_ID` as a cloud env var so
the sync can locate the `notebooklm/` folder.

One-time setup the user does in the cloud environment (relay these if they
haven't; you cannot set them yourself):
- **Env vars**: `NOTION_API_KEY`, `NOTION_DATABASE_ID`,
  `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` (the service-account JSON *as a string*),
  `GOOGLE_SHEETS_SPREADSHEET_ID`, and `AMAZON_EMAIL` / `AMAZON_PASSWORD`
  (`main.load_config()` still requires these even though the manual path is
  unused). ⚠️ The cloud env has no dedicated secret store yet — these are
  readable by anyone who can edit the environment; flag that to the user.
- **Network**: set access to **Full**, or a custom allowlist including
  `api.notion.com` (Google Sheets' `*.googleapis.com` is allowed by default).
- **Deps**: run `deploy/cloud_setup.sh` (or set it as the environment's setup
  script) — it `pip install`s the requirements. No Playwright browser download
  is needed (the manual path never launches a browser).

Then run exactly as in Local mode, e.g.:

```bash
# Step 2 — reconcile the title (read-only "この本ですか？")
python -m scripts.add_manual_highlights --list-books --matches-only --title "<タイトル>"
# Step 4 — dry-run
python -m scripts.add_manual_highlights --input manual_highlights_input.json
# Step 5 — apply
python -m scripts.add_manual_highlights --input manual_highlights_input.json --apply
```

If `import` errors mention a missing package, the setup script has not run —
run `bash deploy/cloud_setup.sh` first. If a Notion write hangs/refuses with a
network error, `api.notion.com` is not allowlisted (see Network above).

## HTTP API mode — drive the deployed web service over HTTP

Use this when you **cannot run the script** (no repo / no env on this surface)
but the deployed Flask service (`deploy/README.md`) is up. It exposes the same
flow as two endpoints, protected by Basic auth.

**Connection details (ask the user once, then reuse in the session):**
- Base URL — the deployed address, e.g. `https://<name>.duckdns.org` (VPS) or
  the Render URL. Do **not** guess it; ask if you don't have it.
- Basic auth — `WEB_USERNAME` / `WEB_PASSWORD` (the same login the web UI uses).
  Pass with `curl -u "$USER:$PASS"`. Treat the password as a secret: don't echo
  it back or write it to a committed file.

The conversation (Step 1 gather, Step 2 reconcile, confirm before writing, Step 5
report honestly) is **unchanged** — only the commands differ.

### Step 2 (remote) — reconcile the title (read-only "この本ですか？")

```bash
curl -s -u "$USER:$PASS" \
  --get "https://<base>/api/manual/books" \
  --data-urlencode "title=ユーザーが言ったタイトル"
```

Returns the same shape as `--list-books --matches-only`:

```json
{"count": 123, "sheets_configured": true, "query_title": "ファストアンドスロー",
 "matches_for_title": [
   {"title": "ファスト&スロー", "score": 0.83, "book_id": "BK-AB12CD", "is_exact_normalized": false}]}
```

Act on it exactly as in Step 2: `is_exact_normalized: true` → reuse that title
silently; a close match → ask 「もしかして既存の『…』ですか？」; no match → new
book. `"sheets_configured": false` means Sheets is off — skip the reconcile and
confirm the spelling with the user directly. Add `&full=1` to also get the whole
`books` list, or `&cutoff=0.5` to widen the net.

### Step 4 (remote) — dry-run, then confirm

The POST body is the **same JSON payload** as the CLI plus an `apply` flag
(default `false` = dry-run). Single book or a `books` array both work.

```bash
curl -s -u "$USER:$PASS" -H "Content-Type: application/json" \
  -X POST "https://<base>/api/manual/highlights" \
  -d '{"title":"ファスト&スロー","source":"physical",
       "highlights":[{"content":"システム1は速い。","page":"42"}]}'
```

The response echoes the plan; show it to the user in Japanese (何冊・何ハイライト
を、どこへ) and ask for confirmation:

```json
{"applied": false, "ok": true, "books": 1, "highlights": 1,
 "targets": ["Notion","Google Sheets"],
 "plan": [{"title":"ファスト&スロー","highlights":1,"source":"physical"}],
 "notion": null, "sheets": null, "problems": []}
```

### Step 5 (remote) — apply, then report honestly

Re-POST the same body with `"apply": true`:

```bash
curl -s -u "$USER:$PASS" -H "Content-Type: application/json" \
  -X POST "https://<base>/api/manual/highlights" \
  -d '{"title":"ファスト&スロー","apply":true,
       "highlights":[{"content":"システム1は速い。","page":"42"}]}'
```

```json
{"applied": true, "ok": true,
 "notion": {"added":1,"skipped":0,"failed":0,"total":1},
 "sheets": {"new_books":1,"new_highlights":1,"skipped_duplicates":0,"skipped_invalid":0,
            "total_notes":1,"missing_files":[],"touched_volumes":1},
 "problems": []}
```

The `sheets` summary comes from the NotebookLM sync (`sync_notes_to_notebooklm`):
`touched_volumes` is how many volume files were rewritten, and `missing_files`
lists any of the 100 files that don't exist yet (those highlights were NOT written).

**Always check `ok`, not just the HTTP status** — a partial write failure still
returns HTTP 200 with `"ok": false` and a populated `problems` array (a missing
volume/index file shows up here). In that case tell the user **in Japanese**
exactly what did not get written and offer to retry; do not report 「追加しました」.
`"sheets": {"not_configured": true}` means only Notion was written (relay that).
Optional body flags: `"notion_only": true` / `"sheets_only": true` to target one
destination. There is no temp file to clean up in remote mode.
