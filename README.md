# kindle2notion

Kindle Notebook のハイライトを取得し、Notion データベースへ保存するツールです。  
必要に応じて Google スプレッドシートにも同時保存できます。

現在は次の 2 つの起動方法に対応しています。

- `python main.py`
  - Tkinter のローカル GUI で実行
- `python web_main.py`
  - Flask の Web 画面で実行

## 機能

- Kindle ハイライトを自動取得
  - 既定は **XHR 直接取得**（クリック巡回なし。従来比 5〜10 倍高速、うまく動かないときは自動でクリック方式にフォールバック）
- **Amazon ログインセッションの再利用**: 一度ログインすれば以後の実行はログイン・2FA なしで数秒で取得開始
- Notion データベースへ保存（重複スキップ付き。重複チェックは **Turso/SQLite キャッシュ** で毎回の全件取得を省略）
- Google スプレッドシート（NotebookLM 用の 99 ボリューム＋索引＝固定 100 ファイル、`k2n_index` / `k2n_vol_*`）へ**取得と同時に自動反映**
- 物理本・他ストアの電子書籍のハイライトを手動追加（`add_manual_highlights.py`、同じ 100 ファイルへ反映）
- Web UI フォーム・HTTP API・Cloud CLI からスマホや外出先で手動ハイライト追加
- 実行履歴の記録（`GET /api/runs`）

### 従来からの挙動変更（重要）

Notion の重複チェックがキャッシュ化されたため、**Notion 側で手動削除したページは次回同期で復活しなくなりました**（従来は復活していました）。復活させたい場合は次のどちらかで「全再同期」してください。

- Web UI: 開始画面の「Notion キャッシュを全再同期してから実行する」にチェック
- CLI: `py -3 -m scripts.resync_notion_cache`

## 前提条件

- Python 3.11 以上がインストールされていること
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

保存先は NotebookLM 用の 100 ファイル（索引 `k2n_index` ＋ ボリューム `k2n_vol_01`〜`k2n_vol_99`）です。**初回だけ 1 回** 用意します。サービスアカウントは Drive にファイルを作成できないため、この作成だけは自分の Google アカウントで行います。GAS スクリプト [`docs/file_maker.js`](docs/file_maker.js) を実行すると、指定フォルダ内に `notebooklm` サブフォルダと 100 ファイルを一括生成できます。作成後、そのフォルダ ID を `config/KEYS.env` の `NOTEBOOKLM_PARENT_FOLDER_ID` に設定してください。

サービスアカウントへのフォルダ共有や dry-run での確認まで含めた手順の全体像は [`docs/NOTEBOOKLM_SETUP_TODO.md`](docs/NOTEBOOKLM_SETUP_TODO.md) を参照してください。

### 5. `config/KEYS.env` を設定する

`config/KEYS.env` に必要情報を記入してください。

```env
# Amazon
AMAZON_EMAIL=
AMAZON_PASSWORD=

# Notion
NOTION_API_KEY=
NOTION_DATABASE_ID=

# Google Sheets（NotebookLM 100 ファイル）を使う場合のみ設定
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=
GOOGLE_SHEETS_SPREADSHEET_ID=
# 100 ファイルを置いた Drive フォルダ ID（推奨。旧マスタ廃止後はこれが主な参照先）
NOTEBOOKLM_PARENT_FOLDER_ID=

# Web UI に Basic 認証を付けたい場合のみ設定
WEB_USERNAME=
WEB_PASSWORD=

# Web サーバーのバインドアドレスとポート（省略時: 0.0.0.0 / 5000）
WEB_HOST=127.0.0.1
WEB_PORT=5000

# Turso（運用DB）を使う場合のみ設定。未設定ならローカルSQLite
# (local_store.db) に自動フォールバックし、セッションはファイルのみ。
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=
```

任意のチューニング用環境変数:

| 変数 | 既定値 | 意味 |
| --- | --- | --- |
| `SCRAPE_MODE` | `xhr` | `dom` で従来のクリック方式を強制 |
| `NOTION_DEDUP_MODE` | `cache` | `scan` で毎回 Notion 全件スキャン（従来挙動） |
| `K2N_LOCAL_DB_PATH` | `local_store.db` | ローカルSQLiteフォールバックの保存先 |
| `CORS_ALLOWED_ORIGINS` | (無効) | Vercel 等の別オリジンのフロントを許可（カンマ区切り・完全一致） |
| `GUNICORN_THREADS` | `8` | 本番サーバーのスレッド数（Docker運用時） |

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
2. 保存済みセッションが有効ならログインをスキップして即取得開始（2回目以降はこちらが通常）
3. セッションがない/切れているときだけ Amazon ログイン（必要なら 2 段階認証）
4. Kindle ハイライトを取得する
5. Notion に保存する
6. Google Sheets 設定があれば Sheets にも保存する

GUI 版では、ログインが必要なときだけブラウザが表示され、Amazon 側の追加認証をブラウザ上でそのまま完了させる想定です（セッション有効時はウィンドウは出ません）。

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
詳細: [`docs/MANUAL_HIGHLIGHTS.md`](docs/MANUAL_HIGHLIGHTS.md)

```bash
# dry-run
py -3 -m scripts.add_manual_highlights --title "本のタイトル" --highlight "ハイライト1" --highlight "ハイライト2"

# JSON ファイルや標準入力からも渡せる
py -3 -m scripts.add_manual_highlights --input book.json
cat book.json | py -3 -m scripts.add_manual_highlights --stdin

# 書き込み確定
py -3 -m scripts.add_manual_highlights --title "..." --highlight "..." --apply

# 既存の本の一覧・類似タイトル検索（タイプミス確認用）
py -3 -m scripts.add_manual_highlights --list-books --title "タイトル"
```

### Notion 重複キャッシュの全再同期 (`resync_notion_cache.py`)

重複チェック用キャッシュを Notion の現状から作り直します。Notion 側でページを手動削除して「次の同期で復活させたい」ときに実行してください。

```bash
py -3 -m scripts.resync_notion_cache
```

### NotebookLM 向け 100 ファイル (`split_per_book.py`)

ハイライトは取得・手動追加と**同時に** NotebookLM 用の 99 ボリューム＋索引（計 100 ファイル）へ自動反映されます（`split_per_book.sync_notes_to_notebooklm`）。`config/KEYS.env` の `NOTEBOOKLM_PARENT_FOLDER_ID` に 100 ファイルを置いた Drive フォルダ ID を設定してください。100 ファイルはサービスアカウントでは作成できないため、初回のみ GAS スクリプト [`docs/file_maker.js`](docs/file_maker.js) を実行して一括作成します（手動で 100 個作成しても可）。  
詳細: [`docs/NOTEBOOKLM_SETUP_TODO.md`](docs/NOTEBOOKLM_SETUP_TODO.md)

```bash
# 索引をボリュームから再構築するだけの安全な保守コマンド（通常は不要）
py -3 -m scripts.split_per_book --apply
```

## デプロイ

推奨構成は **Render（バックエンド）+ Vercel（フロント）+ Turso（運用DB）** です。

> **初めてデプロイする場合はまず [`docs/DEPLOY_TURSO_RENDER_VERCEL.md`](docs/DEPLOY_TURSO_RENDER_VERCEL.md) を読んでください。**

| 方式 | 用途 | 詳細 |
|---|---|---|
| ローカル GUI | 自分の PC で完結 | `python main.py` |
| Render (Docker) | バックエンド本体。Turso 併用で無料プランでも 2FA 再ログイン不要 | [`deploy/render/README.md`](deploy/render/README.md) |
| Vercel (静的) | `frontend/` をそのまま配信するスマホ向け UI | [`deploy/vercel/README.md`](deploy/vercel/README.md) |
| VPS (Ubuntu + Caddy) | 自前サーバー派向け（現在は休止中の旧構成） | [`deploy/README.md`](deploy/README.md) |

## 動かなかったら

`docs/` を確認してください