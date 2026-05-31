# kindle2notion

Kindle Notebook のハイライトを取得し、Notion データベースへ保存するツールです。  
必要に応じて Google スプレッドシートにも同時保存できます。

現在は次の 2 つの起動方法に対応しています。

- `python main.py`
  - Tkinter のローカル GUI で実行
- `python web_main.py`
  - Flask の Web 画面で実行

## 前提条件

- Python がインストールされていること
- `pip install -r requirements/requirements.txt` を実行済みであること
- Playwright の Chromium をインストール済みであること

```bash
playwright install chromium
```

## セットアップ

### 1. Notion データベースを用意する

保存先の Notion データベースには、少なくとも次の 3 プロパティが必要です。

| Property | Type |
| --- | --- |
| `Title` | Title |
| `Content` | Rich text |
| `Page` | Rich text |

プロパティ名はコード内で固定されているため、名前を変える場合は `notion/toNotion.py` も合わせて修正してください。

### 2. Notion API キーを用意する

Notion の Integration を作成して API キーを取得してください。

- 参考: https://www.notion.so/profile/integrations

### 3. Notion Database ID を確認する

データベース URL の `https://www.notion.so/<DATABASE_ID>?v=...` の部分が `NOTION_DATABASE_ID` です。

### 4. Google Sheets を使う場合の準備

Google Sheets 保存は任意です。使わない場合は設定不要です。

`DOCUMENTS/NOTEBOOKLM_SETUP_TODO.md` に記載されています。

### 5. `config/KEYS.env` を設定する

`config/KEYS.env` に必要情報を記入してください。

```env
# Amazon
AMAZON_EMAIL=
AMAZON_PASSWORD=

# Notion
NOTION_API_KEY=
NOTION_DATABASE_ID=

# Google Sheets を使う場合のみ設定
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=
# Worksheet 名は v2 で固定なので GOOGLE_SHEETS_WORKSHEET_NAME は廃止
GOOGLE_SHEETS_SPREADSHEET_ID=

# Web UI に Basic 認証を付けたい場合のみ設定
WEB_USERNAME=
WEB_PASSWORD=
```

`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` は次のどちらでも使えます。

- Service Account JSON ファイルのパス
- JSON 本文そのもの

Windows ではまずファイルパス指定をおすすめします。

例:

```env
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=C:\Users\<user>\Downloads\service-account.json
```

### 6. Amazon 側の前提

Amazon アカウントで Kindle Notebook が利用できることを確認してください。
このリポジトリは日本で作成された Amazon アカウントのみをサポートしています。

- https://read.amazon.co.jp/notebook

## 実行方法

### ローカル GUI 版

```bash
python main.py
```

流れ:

1. 取得する書籍数を入力する
2. Amazon にログインする
3. 必要なら、表示された Chromium 側で 2 段階認証コードを入力する
4. Kindle ハイライトを取得する
5. Notion に保存する
6. Google Sheets 設定があれば Sheets にも保存する

GUI 版では、ログイン用ブラウザを表示している間は、Amazon 側の追加認証をブラウザ上でそのまま完了させる想定です。

### Web 版

```bash
python web_main.py
```

起動後、同じマシンまたは同一ネットワーク上の端末から次へアクセスできます。

```text
http://<server-ip>:5000
```

## 動かなかったら

### 1. Notion への保存で失敗する

確認ポイント:

- `NOTION_API_KEY` が正しいか
- `NOTION_DATABASE_ID` が正しいか
- Integration にデータベースへのアクセス権があるか
- Notion データベースに `Title / Content / Page` があるか

### 2. Google Sheets で `403` や `PermissionError` が出る

確認ポイント:

- `Google Sheets API` と `Google Drive API` を有効にしたか
- Spreadsheet を Service Account に共有したか
- `GOOGLE_SHEETS_SPREADSHEET_ID` が正しいか
- `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` のパスや JSON が正しいか

### 3. `OSError: [Errno 22] Invalid argument` が出る

`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` に壊れた JSON 文字列を入れている可能性があります。  
まずは JSON ファイルのパス指定に切り替えて確認してください。

### 4. Playwright 関連で起動できない

次を再実行してください。

```bash
playwright install chromium
```

### 5. `split_per_book.py` で `403 Forbidden` / `storageQuotaExceeded` が出る

Service Account は個人 Drive の容量を持たないため、"My Drive" 配下に
スプレッドシートを新規作成できません。本スクリプトはファイル作成を行わず
**既存ファイルへの書き込みのみ** を行う設計になっています。

対処:

- 親フォルダの `notebooklm/` 配下に、dry-run で表示された固定 50 個のファイル名と
  完全一致する Google Sheets を **一度だけ手動で作成** してから `--apply` を実行する
- 親フォルダ自体を Service Account の編集者権限で共有しておく
  (これによりフォルダ内に作ったシートも自動的に編集可能になる)

詳細は上記「NotebookLM 用に固定ボリュームファイルへ分割」を参照。

### 6. `split_per_book.py` で `--parent-folder` の検証エラーが出る

次のいずれかが原因です。

- 渡した ID が **フォルダではなくスプレッドシートの ID** になっている
  (URL の `/folders/<ID>` 部分を渡してください。`/d/<ID>/edit` ではなく)
- フォルダが Service Account に共有されていない、または閲覧者権限のみ
  → Service Account のメールアドレスに **編集者** で共有し直してください