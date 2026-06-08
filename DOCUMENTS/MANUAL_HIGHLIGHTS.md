# 手動ハイライト追加ガイド (`add_manual_highlights.py`)

Kindle 以外の本（紙の本・他ストアの電子書籍・図書館の本など）のハイライトを
Notion と Google Sheets（`01_books` / `02_highlights`）に追加するスクリプトです。

---

## 入力方式

3 種類のどれか 1 つを選んで使います。

### 1. CLI 引数（クイック入力）

```bash
py -3 -m scripts.add_manual_highlights \
  --title "ファスト&スロー" \
  --highlight "人間の判断は2つのシステムで構成される" \
  --highlight "システム1は速く直感的、システム2は遅く論理的"
```

### 2. JSON ファイル

```bash
py -3 -m scripts.add_manual_highlights --input book.json
```

### 3. 標準入力

```bash
cat book.json | py -3 -m scripts.add_manual_highlights --stdin
```

---

## JSON ペイロード形式

複数冊をまとめて渡す場合は `books` 配列を使います。1冊だけなら配列ごと省略できます。

```json
{
  "books": [
    {
      "title": "ファスト&スロー",
      "author": "ダニエル・カーネマン",
      "genre": "behavioral economics",
      "reading_status": "読了",
      "finished_at": "2026-05-30",
      "rating": "5",
      "source": "physical",
      "highlights": [
        {"content": "ハイライト本文", "page": "42"},
        {"content": "別の本文", "location": "1200-1210"},
        "本文だけの文字列でもOK"
      ]
    }
  ]
}
```

### 本フィールド一覧

| フィールド | 必須 | 説明 |
|---|---|---|
| `title` | ✅ | 本のタイトル（book_id の元になるので表記を統一する） |
| `highlights` | ✅ | ハイライトの配列（1件以上） |
| `author` | — | 著者名 |
| `genre` | — | ジャンル |
| `reading_status` | — | 読書状態（例: `"読了"`, `"読中"`） |
| `finished_at` | — | 読了日（ISO 8601: `"2026-05-30"`） |
| `rating` | — | 評価（文字列） |
| `amazon_asin` | — | Amazon ASIN |
| `cover_url` | — | 表紙画像 URL |
| `notion_url` | — | 対応する Notion ページ URL |
| `source` | — | ハイライト元（デフォルト: `"manual"`, 紙の本: `"physical"`） |

本メタデータ（`author` 以下）は **本行が初めて作成されるときのみ** 書き込まれます。

### ハイライトフィールド一覧

| フィールド | 必須 | 説明 |
|---|---|---|
| `content` | ✅ | ハイライト本文 |
| `page` | — | ページ番号 |
| `location` | — | Kindle ロケーション（`page` が空のとき Notion の Page 欄に入る） |
| `highlighted_at` | — | ハイライト日（ISO 8601） |
| `source` | — | 本単位の `source` を上書きしたい場合に指定 |

ハイライトは文字列 `"本文"` だけでも渡せます（`page` / `location` なしで追加）。

---

## タイトル重複チェック（`--list-books`）

タイトルを間違えると別の本として登録されてしまいます。追加前に既存の本と照合してください。

```bash
# 全件一覧
py -3 -m scripts.add_manual_highlights --list-books

# 類似タイトル検索（入力に近い候補をスコア順で表示）
py -3 -m scripts.add_manual_highlights --list-books --title "ファストアンドスロー"
```

`score` が 1.0 なら正規化後に完全一致（全角/半角・スペース・記号の違いは無視されます）。

---

## ドライランと `--apply`

デフォルトは **ドライラン**（書き込みなし）。内容を確認してから `--apply` で確定します。

```bash
# 1. まず dry-run で確認
py -3 -m scripts.add_manual_highlights --input book.json

# 2. 問題なければ apply
py -3 -m scripts.add_manual_highlights --input book.json --apply
```

同じ内容を再実行しても安全です（重複はスキップされます）。

---

## 書き込み先の絞り込み

```bash
--notion-only    # Notion にだけ書く
--sheets-only    # Google Sheets にだけ書く
```

---

## スマホから追加する（3つの経路）

外出先で PC のコマンドが使えないときは、以下のいずれかで同じことができます。
どれも同じ Notion / Google Sheets に書き込まれ、重複は自動でスキップされます。

### 方法 1: クラウドの Claude Code から（環境変数 + 既存 CLI を直接実行）

サーバー常駐が不要で最も軽量。claude.ai/code のクラウド環境にこのリポジトリを
接続し、シークレットを環境変数として保存すると、スマホの Claude Code が PC と
同じ CLI（`python -m scripts.add_manual_highlights ...`）をそのまま実行できます。

1. claude.ai/code でこの GitHub リポジトリを接続する。
2. 環境変数（Environment variables）に設定:
   `NOTION_API_KEY` / `NOTION_DATABASE_ID` /
   `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE`（サービスアカウント JSON を文字列で）/
   `GOOGLE_SHEETS_SPREADSHEET_ID` / `AMAZON_EMAIL` / `AMAZON_PASSWORD`
   （Amazon 認証情報は手動パスでは未使用だが `main.load_config()` が必須にしている）。
3. ネットワークを **Full**、または `api.notion.com` を許可リストに追加
   （Google Sheets の `*.googleapis.com` は既定で許可済み）。
4. 依存を入れる: 環境の Setup script に `deploy/cloud_setup.sh` を指定（または
   `bash deploy/cloud_setup.sh` を実行）。Playwright のブラウザ本体は不要。
5. あとは Claude に「この本のハイライト追加して」と頼むだけ（スキル
   `adding-manual-highlights` の *Cloud mode* に従って、あいまい検索で
   「この本ですか？」と確認 → dry-run → apply）。

> ⚠️ クラウド環境の環境変数は**専用のシークレット保管庫がまだ無く**、その環境を
> 編集できる人には見えます。サービスアカウントの秘密鍵 JSON や Notion キーを
> 置くことになるので、その前提で利用してください。

### 方法 2: スマホのブラウザからフォームで入力（Claude 不要）

デプロイ済み Web サービス（`deploy/README.md`、Basic 認証
`WEB_USERNAME` / `WEB_PASSWORD`）を使います。

1. デプロイ先の URL（例 `https://<名前>.duckdns.org`）を開く。
2. 開始画面の **「紙の本のハイライトを手動で追加」** を押す。
3. 本のタイトルを入れて **「既存の本を検索（この本ですか？）」** を押すと、
   表記の近い既存の本が候補表示されます。同じ本ならタップして正式タイトルを採用。
4. ハイライトを1行に1つ入力 → **「内容を確認」**（プレビュー）→ **「この内容で追加する」**。

### 方法 3: HTTP API を curl（デプロイ済みサービス / 任意クライアント）

Claude Code 以外の場所からでも、デプロイ済みサービスの API を直接叩けます。

```bash
# 類似タイトル検索（読み取り専用 / この本ですか？）
curl -s -u "$USER:$PASS" --get "https://<base>/api/manual/books" \
  --data-urlencode "title=ファストアンドスロー"

# 追加（apply 省略時は dry-run。確認後に "apply": true で確定）
curl -s -u "$USER:$PASS" -H "Content-Type: application/json" \
  -X POST "https://<base>/api/manual/highlights" \
  -d '{"title":"ファスト&スロー","apply":true,
       "highlights":[{"content":"システム1は速い。","page":"42"}]}'
```

`POST /api/manual/highlights` は部分失敗でも HTTP 200 を返し、`"ok": false` と
`problems` で知らせます。**ステータスコードだけでなく `ok` を必ず確認**してください。

---

## 注意事項

- **タイトルの表記を変えると `book_id` が変わり、別の本として登録されます。**  
  追加前に必ず `--list-books --title "..."`（または `GET /api/manual/books?title=...`）で既存の表記を確認してください。
- 本メタデータ（著者・ジャンルなど）は初回作成時のみ有効です。既存の本行には上書きされません。
