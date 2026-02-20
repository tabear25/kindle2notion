# これは何（What's this?）
Kindleのハイライトを取得し、NotionのDBに格納するシステムです。

# 前提条件（Prerequisites）
 [Kindle メモとハイライト](https://read.amazon.co.jp/notebook) を利用します。  
AmazonアカウントとNotionアカウントが必要です。
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

4. **Amazon アカウントの ID / PW を確認する**
   - Kindle ハイライトにアクセスできるアカウント情報を使ってください。

5. **環境変数ファイルを作成する**
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
   ```

6. **Playwright のブラウザをインストールする**
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

### 注意点（Notes）
- 既存の `Content` と同じテキストは重複登録をスキップします。
- セッション情報は `storage_state.json` に保存されます。
- Amazon / Notion 側の画面構成変更で動作しなくなる可能性があります。
