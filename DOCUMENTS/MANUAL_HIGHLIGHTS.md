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

## 注意事項

- **タイトルの表記を変えると `book_id` が変わり、別の本として登録されます。**  
  追加前に必ず `--list-books --title "..."` で既存の表記を確認してください。
- 本メタデータ（著者・ジャンルなど）は初回作成時のみ有効です。既存の本行には上書きされません。
