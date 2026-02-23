# これは何（What's this?）
Kindleのハイライトを取得し、NotionのDBに格納するシステムです。  
Google スプレッドシートへの保存にも対応しています（Notion保存後に続けて保存）。

# 前提条件（Prerequisites）
 [Kindle メモとハイライト](https://read.amazon.co.jp/notebook) を利用します。  
AmazonアカウントとNotionアカウントが必要です。
Google スプレッドシートにも保存する場合は、Googleアカウント / Google Cloud の設定も必要です。
このリポジトリは日本のAmazonアカウントでの利用を想定しているので、用意するAmazonアカウントは日本で作成されたものである必要があります。

## 必要なライブラリ（Required Libraries）
`requirements/requirements.txt` にまとめてあるので、インストールしてください。

# 使い方（How to Use）

### 1. 準備（Preparation）
1. **Notion でデータベース（=DB）を作成する**
   - Notion 上で DB を作成してください。
   - DBのフォーマットは以下の通りにしてください。
   - 最初の3列はこのフォーマットで作成してください。

   | Title  | Content | Page  |
   |-------|------|-------|

2. **Notion API（無料）を取得する**
   - [Notion API](https://www.notion.so/profile/integrations) から Integrationを作成し、API Keyを控えてください。

3. **DBID（無料）を取得する**
   - 1 で作成した DB の ID（=DBID）を取得します。
   - 共有 URL の以下部分が DBID です。
   ```
   https://www.notion.so/<DBID>?v=<ビューID>
   ```

4. **Google スプレッドシート（任意）を使う場合の準備**
   - [Google Cloud Console](https://console.cloud.google.com)を開く
   - Google Cloud Console でプロジェクトを作成してください。
   - **重要**: 以降の API 有効化 / Service Account 作成は、必ず同じプロジェクトで行ってください。
     - プロジェクトがズレると、API を有効化したのに使えない（`403`）状態になります。
   - Google Cloud Console の左メニューから「API とサービス」→「ライブラリ」を開き、以下を有効化してください。
     - `Google Sheets API`
     - `Google Drive API`
     - 各APIのページで「有効にする」ボタンを押します。
     - 有効化した直後は反映に数分かかることがあります。
   - Google Cloud Console の左メニューから「IAM と管理」→「サービス アカウント」を開いてください。
   - 「サービス アカウントを作成」を押して、Service Account を作成してください。
     - 名前: 分かりやすい名前でOK（例: `kindle2spreadsheet`）
     - ロール: このスクリプトではスプレッドシート側の共有権限で制御するため、ここは細かく迷わなくても大丈夫です。
   - 作成した Service Account をクリックし、「キー」タブ（または「鍵」）から JSON キーを発行してください。
     - 「鍵を追加」→「新しい鍵を作成」→「JSON」→ 作成
   - JSON キーのダウンロードが始まるので、JSON ファイルを保存してください。
   - 保存先の Google スプレッドシートを作成してください。
   - 作成したスプレッドシート右上の「共有」から、Service Account のメールアドレスを追加し、`編集者` 権限を付与してください。
     - Service Account のメールアドレスは、以下のような形式です。
       - `xxxxx@xxxxx.iam.gserviceaccount.com`
     - 共有先として「自分のGoogleアカウント」ではなく、**Service Account のメールアドレス**を入れる点に注意してください。
     - 共有していないと、実行時に `PermissionError` / `403` が発生します。
   - スプレッドシートID（`GOOGLE_SHEETS_SPREADSHEET_ID`）は URL の以下部分です。
   ```
   https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit#gid=0
   ```
   - 例:
   ```
   https://docs.google.com/spreadsheets/d/14NpdB-IrEwoF1LJIpe1gpHgB7uvmMQwkes4BU3KAy4M/edit?gid=0#gid=0
   ```
   - この例の `GOOGLE_SHEETS_SPREADSHEET_ID` は以下です。
   ```
   14NpdB-IrEwoF1LJIpe1gpHgB7uvmMQwkes4BU3KAy4M
   ```
   - `gid=0` の `0` はワークシート（タブ）のIDであり、`GOOGLE_SHEETS_SPREADSHEET_ID` ではありません。
   - スプレッドシートのフォーマットは Notion と同じく以下を先頭3列にしてください（未作成でも、空シートならヘッダ行を自動追加します）。

   | Title  | Content | Page  |
   |-------|------|-------|
   - ワークシート名（タブ名）は `GOOGLE_SHEETS_WORKSHEET_NAME` で指定できます（未指定時は `Sheet1`）。
   - 指定したワークシートが存在しない場合は、自動で新規作成します。

5. **Amazon アカウントの ID / PW を確認する**
   - Kindle ハイライトにアクセスできるアカウント情報を使ってください。

6. **環境変数ファイルを作成する**
   - `config/KEYS.env` を作成し、以下のフォーマットで記述してください。
   ```
   # AmazonアカウントのID
   AMAZON_EMAIL=
   # Amazonアカウントのパスワード
   AMAZON_PASSWORD=
   # Notion APIキー
   NOTION_API_KEY=
   # Notion DBのID
   NOTION_DATABASE_ID=

   # Google スプレッドシート保存を使う場合（任意）
   # Service Account JSONキーのファイルパス（推奨）
   # 例: C:\Users\<ユーザー名>\Downloads\service-account.json
   GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=
   # スプレッドシートURLの /d/<ここ>/edit の部分
   GOOGLE_SHEETS_SPREADSHEET_ID=
   # ワークシート名（任意。未指定時は Sheet1）
   GOOGLE_SHEETS_WORKSHEET_NAME=Sheet1
   ```
   - `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` は **JSON本文そのものではなく、JSONファイルのパス** を設定する運用を推奨します。
   - 他の記事やメモで `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE_ENV` という名前を見かけることがありますが、このプロジェクトのコードが読み込むのは `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` です。
   - Windows のパスは以下のようにそのまま書けます。
   ```
   GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=C:\Users\<ユーザー名>\Downloads\service-account.json
   ```
   - `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` に JSON の中身（`{ ... }` 全体）を直接入れる方法もありますが、非エンジニア向けの運用ではミスが増えやすいため非推奨です。
     - 改行や引用符、`\n` の扱いで崩れやすい
     - `.env` ファイルが長くなり、編集ミスしやすい
   - Google スプレッドシート保存を使わない場合は、`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` と `GOOGLE_SHEETS_SPREADSHEET_ID` は未設定のままにしてください。
   - Google スプレッドシート保存を使う場合は、`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` と `GOOGLE_SHEETS_SPREADSHEET_ID` を両方設定してください
   - `GOOGLE_SHEETS_WORKSHEET_NAME` は省略できます。省略した場合は `Sheet1` が使われます。

7. **Playwright のブラウザをインストールする**
   - 初回のみ実行してください。
   ```
   playwright install chromium
   ```

### 2. 実行する（Run the Script）
1. `kindle2notion` ディレクトリで実行します。
   ```
   python main.py
   ```
2. 起動後、GUI ダイアログで「何冊分スクレイピングするか」を入力します。
   - 正の整数: 指定冊数だけ処理
   - 空欄: 全冊処理
   - キャンセル: 実行中止
3. Amazonへログインします。
4. 2段階認証が表示された場合は認証を完了してください（待機時間は `amazon/login.py` の `TWO_FACTOR_WAIT_MS`）。
5. 取得後、Notionへの保存が実行されます。
6. Google スプレッドシート用の環境変数が設定されている場合は、続けてGoogle スプレッドシートにも保存されます。

### 注意点（Notes）
- Notion / Google スプレッドシートともに、既存の `Content` と同じテキストは重複登録をスキップします。
- Google スプレッドシートの保存には、スプレッドシートを Service Account に共有している必要があります。
- Google Cloud 側で `Google Sheets API` / `Google Drive API` が無効だと保存に失敗します。
- `Google Sheets API has not been used in project ... before or it is disabled` と表示された場合は、Service Account を作成した Google Cloud プロジェクトで `Google Sheets API` を有効化してください（有効化直後は数分待って再実行）。
- `PermissionError` / `403` が出た場合は、以下を確認してください。
  - `GOOGLE_SHEETS_SPREADSHEET_ID` が正しいか（URL全体ではなくID部分）
  - スプレッドシートを Service Account のメールアドレスに `編集者` 権限で共有しているか
  - `Google Drive API` も有効化しているか
- `OSError: [Errno 22] Invalid argument` のようなエラーで、パスの中に `{ "type": "service_account", ... }` のような JSON が見えている場合は、`GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` に「JSONファイルのパス」ではなく「JSON本文」を入れてしまっている可能性があります。
- Service Account の JSON キー（特に `private_key`）をチャット・画面共有・公開リポジトリに出してしまった場合は、Google Cloud Console でそのキーを削除し、新しいキーを再発行してください。
- セッション情報は `storage_state.json` に保存されます。
- Amazon / Notion / Google 側の画面構成・API仕様変更で動作しなくなる可能性があります。