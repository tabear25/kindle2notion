# kindle2notion

Kindle Notebook のハイライトを取得し、Notion データベースへ保存するツールです。  
必要に応じて Google Sheets にも同時保存できます。

現在は次の 2 つの起動方法に対応しています。

- `python main.py`
  - Tkinter のローカル GUI で実行
- `python web_main.py`
  - Flask の Web 画面で実行

## できること

- Amazon Kindle Notebook からハイライトを取得
- Notion データベースへ保存
- Google Sheets へ任意で保存
- Amazon の 2 段階認証コード入力に対応
- 同じ `Title / Content / Page` の組み合わせは重複保存しない

## 動作確認の状況

2026-04-17 時点で、ローカルで次を確認済みです。

- Python の構文チェック: `python -m compileall .`
- テスト: `python -m pytest test -q -p no:cacheprovider`
- 結果: `5 passed`
- Flask の最低限の起動確認
  - `/` が `200`
  - 不正な `max_books` を送ると `/api/start` が `400`
- `main.load_config()` が現在の `config/KEYS.env` を読めること

未確認のもの:

- Amazon への実ログイン
- Kindle Notebook の実スクレイピング
- Notion API への実保存
- Google Sheets API への実保存

この 4 点は、実アカウント情報とネットワーク接続が必要です。

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

必要なもの:

- Google Cloud の Service Account
- Service Account の JSON キー
- 保存先 Spreadsheet の ID

補足:

- `Google Sheets API`
- `Google Drive API`

の両方を有効化してください。

さらに、保存先スプレッドシートを Service Account のメールアドレスに共有してください。  
共有しないと `403` や `PermissionError` になります。

Spreadsheet ID は URL の `/d/<SPREADSHEET_ID>/edit` の部分です。

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
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SHEETS_WORKSHEET_NAME=Sheet1

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

補足:

- `WEB_USERNAME` と `WEB_PASSWORD` を設定すると Basic 認証が有効になります
- Web 版でも 2 段階認証コードを画面から入力できます

### 外出先からアクセスする (VPS デプロイ)

同じ Wi-Fi 外からスマホで利用したい場合は、無料枠のクラウド VPS に常駐させ、Caddy (自動 HTTPS) + DuckDNS (無料サブドメイン) 経由で公開できます。GitHub Actions を使って `main` に push するだけで自動デプロイされる構成です。

手順とファイル:

- 詳細ガイド: [`deploy/README.md`](deploy/README.md)
- 構成ファイル一式: `deploy/` と `.github/workflows/deploy.yml`

外部公開する場合は **必ず `WEB_USERNAME` / `WEB_PASSWORD` を設定**してください (未設定だと認証なしで誰でもアクセス可能)。

## 手動で行う必要がある設定 (外部公開デプロイ向け)

VPS へのデプロイには、スクリプトで自動化できない手動操作が 8 つあります。詳細な手順は [`deploy/README.md`](deploy/README.md) を参照してください。ここには必要な項目の一覧のみを掲載します。

1. **クラウド VPS のアカウント作成とインスタンス起動** — Oracle Cloud Always Free (Ampere A1) または GCP e2-micro を選択し、Ubuntu 24.04 LTS でパブリック IP を確保する
2. **DuckDNS のサブドメイン取得** — 無料サブドメインを予約し、発行された **トークン** をメモする
3. **SSH 鍵ペアの生成と VPS への登録** — `ssh-keygen` で鍵を作り公開鍵を VPS に配置、パスワード認証と root ログインを無効化する
4. **VPS 上での初回セットアップ** — リポジトリを `/opt/kindle2notion` に clone し `deploy/setup.sh` を実行、DuckDNS トークン配置と `Caddyfile` のドメイン書き換えを行う
5. **`config/KEYS.env` の作成 (VPS 上のみ、Git には含めない)** — Amazon / Notion / (任意) Google Sheets の資格情報に加え、**`WEB_USERNAME`** と **`WEB_PASSWORD`** (長いランダム文字列)、`WEB_HOST=127.0.0.1` を記入する
6. **Notion / Amazon / Google シートの各種資格情報の取得** — 上記「セットアップ」セクションを参照しつつ、それぞれのアカウント情報と API キーを準備する
7. **GitHub リポジトリの Secrets 登録** — `VPS_HOST` / `VPS_USER` / `VPS_SSH_KEY` (必要なら `VPS_PORT`) をリポジトリの Actions Secrets に登録する
8. **初回動作確認** — `systemctl start kindle2notion-web` でサービスを起動し、スマホのモバイル回線から DuckDNS の URL にアクセスして Basic 認証とパイプライン動作を確認する

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

## リファクタリング内容

今回の更新で次を調整しています。

- 設定ファイル読み込みを `config/__init__.py` に集約
- Notion / Google Sheets の重複判定を `Title / Content / Page` ベースに統一
- Web 版の入力値バリデーションを追加
- SSE のエラーイベント名を分離して、接続エラーと業務エラーを区別
- Tkinter / Web UI の文字化けを解消
- テストを自動収集されるファイル名に修正

## まだ必要な情報

このコードを本番に近い形で最終確認するには、次の情報と状態が必要です。

- 有効な Amazon アカウント
- Kindle Notebook に実際のハイライトが存在すること
- 有効な Notion API キーと Database ID
- Google Sheets を使うなら Service Account と共有済み Spreadsheet

ここまで揃えば、実データでの最終確認は次の順で進めるのがおすすめです。

1. `python main.py` で 1 冊だけ指定して試す
2. Notion に 1 件以上保存されることを確認する
3. Google Sheets を使う場合は Sheets 側も確認する
4. 問題なければ冊数制限を外して全件実行する
