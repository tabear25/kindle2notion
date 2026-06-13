# kindle2notion

Kindle Notebook のハイライトを取得し、Notion データベースへ保存するツールです。  
必要に応じて Google スプレッドシートにも同時保存できます。

現在は次の 2 つの起動方法に対応しています。

- `python main.py`
  - Tkinter のローカル GUI で実行
- `python web_main.py`
  - Flask の Web 画面で実行

## 機能

- Kindle ノートブックからハイライトを自動取得（Playwright スクレイピング）
- Notion データベースへ保存（重複スキップ付き）
- Google スプレッドシート（NotebookLM 用の 49 ボリューム＋索引＝固定 50 ファイル）へ取得と同時に自動反映（`split_per_book.py`）
- 物理本・他ストアの電子書籍のハイライトを手動追加（`add_manual_highlights.py`、同じ 50 ファイルへ反映）
- Web UI フォーム・HTTP API・Cloud CLI からスマホや外出先で手動ハイライト追加

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

# Google Sheets（NotebookLM 50 ファイル）を使う場合のみ設定
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=
GOOGLE_SHEETS_SPREADSHEET_ID=
# 50 ファイルを置いた Drive フォルダ ID（推奨。旧マスタ廃止後はこれが主な参照先）
NOTEBOOKLM_PARENT_FOLDER_ID=

# Web UI に Basic 認証を付けたい場合のみ設定
WEB_USERNAME=
WEB_PASSWORD=

# Web サーバーのバインドアドレスとポート（省略時: 0.0.0.0 / 5000）
WEB_HOST=127.0.0.1
WEB_PORT=5000
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

## ユーティリティスクリプト

### 手動ハイライト追加 (`add_manual_highlights.py`)

Kindle 以外の本（紙の本・他ストアの電子書籍）のハイライトを Notion / Google Sheets に追加します。  
スマホや外出先からも **Web フォーム・HTTP API・Cloud CLI** の 3 経路で使えます。  
詳細: [`DOCUMENTS/MANUAL_HIGHLIGHTS.md`](DOCUMENTS/MANUAL_HIGHLIGHTS.md)

```bash
# ドライラン（確認のみ）
py -3 -m scripts.add_manual_highlights --title "本のタイトル" --highlight "ハイライト1" --highlight "ハイライト2"

# JSON ファイルや標準入力からも渡せる
py -3 -m scripts.add_manual_highlights --input book.json
cat book.json | py -3 -m scripts.add_manual_highlights --stdin

# 書き込み確定
py -3 -m scripts.add_manual_highlights --title "..." --highlight "..." --apply

# 既存の本の一覧・類似タイトル検索（タイプミス確認用）
py -3 -m scripts.add_manual_highlights --list-books --title "タイトル"
```

### NotebookLM 向け 50 ファイル (`split_per_book.py`)

ハイライトは取得・手動追加と**同時に** NotebookLM 用の 49 ボリューム＋索引（計 50 ファイル）へ自動反映されます（`split_per_book.sync_notes_to_notebooklm`）。`config/KEYS.env` の `NOTEBOOKLM_PARENT_FOLDER_ID` に 50 ファイルを置いた Drive フォルダ ID を設定してください。50 ファイルはサービスアカウントでは作成できないため、初回のみ手動で空シートを作成します。  
詳細: [`DOCUMENTS/NOTEBOOKLM_SETUP_TODO.md`](DOCUMENTS/NOTEBOOKLM_SETUP_TODO.md)

```bash
# 索引をボリュームから再構築するだけの安全な保守コマンド（通常は不要）
py -3 -m scripts.split_per_book --apply
```

> 旧マスタ（`01_books` / `02_highlights`）は廃止済みです。`--from-master` は旧マスタから 50 ファイルを上書きする**レガシー専用**フラグで、最近のハイライトを失う恐れがあるため通常は使いません。`migrate_legacy_sheet.py` も同様に非推奨です。

## デプロイ

| 方式 | 用途 | 詳細 |
|---|---|---|
| ローカル GUI | 自分の PC で完結 | `python main.py` |
| ローカル Web UI | 同一 Wi-Fi 内のスマホから操作 | `python web_main.py` |
| VPS (Ubuntu + Caddy) | 外出先からでも使いたい | [`deploy/README.md`](deploy/README.md) |
| Render (Docker) | サーバーを持ちたくない | [`deploy/render/README.md`](deploy/render/README.md) |

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

詳細は [`DOCUMENTS/NOTEBOOKLM_SETUP_TODO.md`](DOCUMENTS/NOTEBOOKLM_SETUP_TODO.md) を参照。

### 6. `split_per_book.py` で `--parent-folder` の検証エラーが出る

次のいずれかが原因です。

- 渡した ID が **フォルダではなくスプレッドシートの ID** になっている
  (URL の `/folders/<ID>` 部分を渡してください。`/d/<ID>/edit` ではなく)
- フォルダが Service Account に共有されていない、または閲覧者権限のみ
  → Service Account のメールアドレスに **編集者** で共有し直してください