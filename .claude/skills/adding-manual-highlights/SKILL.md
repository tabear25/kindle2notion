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
in conversation and write them with `scripts/add_manual_highlights.py`, which
reuses the exact same Notion + Google Sheets writers as the Kindle sync. The
output is indistinguishable from scraped highlights except for the `source`
column on `02_highlights`.

Always converse with the user in **Japanese** (this is a Japanese user).

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

Optional book metadata (only stored on Google Sheets `01_books`, only when the
book is newly created — ask lightly, don't force it):
- `author` 著者 / `genre` ジャンル / `reading_status` 読書状況（例: 読了）/
  `finished_at` 読了日（YYYY-MM-DD）/ `rating` 評価 / `amazon_asin` / `cover_url` /
  `notion_url`
- `source` — defaults to `"manual"`. Use `"physical"` for paper books if helpful.

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
> (it reads from `01_books`). In that case skip the reconcile and just confirm
> the title spelling directly with the user before continuing.

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
  property. On Google Sheets `02_highlights`, a page-only highlight is stored in
  the **`location`** column (the `page` column is reserved for highlights that
  also carry a Kindle `location`). The value is never lost — it is just stored
  under `location` for page-only entries, mirroring how Kindle-scraped rows
  behave, so manual and scraped highlights stay consistent.

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

## Step 6 — Clean up

Delete the temporary `*.json` input file after a successful run (it is
git-ignored but leaving it around is untidy). Confirm to the user what was added.

## Notes / gotchas

- The Python launcher on this machine is `py` (not `python`). Run scripts as
  `py -m scripts.add_manual_highlights ...` from the project root.
- Book metadata (`author`, etc.) is written to `01_books` **only when the book row
  is first created**. Adding more highlights later does not overwrite it; the user
  edits the sheet directly to change metadata.
- Notion stores only Title / Content / Page (no author/source). The richer
  metadata lives on Google Sheets `01_books`.
- This never runs the Kindle scraper and never touches `storage_state.json`.
