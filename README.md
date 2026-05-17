# kindle2notion

Kindle Notebook のハイライトを取得し、Notion データベースへ保存するツールです。  
必要に応じて Google Sheets にも同時保存できます。

> 📘 **はじめての方 (Windows ユーザー向け / 完全初心者OK)**: [SETUP_GUIDE.md](./SETUP_GUIDE.md) を上から順に読めば、ゼロから「スマホで URL アクセスできる状態」まで到達できます。

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

#### Sheets スキーマ (v2)

このリポジトリは AI 検索しやすい多シート構成で書き込みます。シート名は固定で、`google_sheets/toSheets.py` が自動的に作成・ヘッダ修復します。

| シート名 | 1 行の意味 | 書き込む側 |
| --- | --- | --- |
| `01_books` | 1 書籍 | **kindle2notion** |
| `02_highlights` | 1 ハイライト | **kindle2notion** |
| `03_book_summary` | 1 書籍の AI 要約 | Claude (任意・別途) |
| `04_highlight_tags` | 1 ハイライト × 1 タグ (long 形式) | Claude (任意・別途) |
| `05_tags_taxonomy` | タグ語彙 | 人間 + Claude |

主キー:

- `book_id` = `BK-` + SHA1(title)\[0:6\] (大文字)。タイトル文字列が変わらない限り安定。
- `highlight_id` = `HL-<book6>-<NNNN>` (NNNN は書籍内 1 始まり連番)。
- 重複判定キーは `(book_id, sha1(content))`。

不変条件 (絶対):

1. `kindle2notion` は `01_books` と `02_highlights` のみ書き込む。
2. AI が埋める `03` / `04` / `05` には一切触れない。
3. 旧 `Sheet1` は read-only。書き換えない。
4. 既存行の `book_id` / `highlight_id` を後から書き換えない (移行スクリプトで一発で確定する)。

旧 `Sheet1` から v2 へのワンショット移行は `scripts/migrate_legacy_sheet.py` で行えます。

```bash
python -m scripts.migrate_legacy_sheet            # dry-run
python -m scripts.migrate_legacy_sheet --apply    # 実行
```

#### NotebookLM 用に固定ボリュームファイルへ分割

NotebookLM は 1 つのノートブックに取り込めるソースを **50 個まで**に制限しています。
「1 冊 1 ファイル」では 51 冊目以降が追加できなくなるため、
`scripts/split_per_book.py` は冊数に関係なく **常に 50 ファイル固定**の構成で出力します。

- **コンテンツ 49 ファイル (ボリューム)** + **索引 1 ファイル** = 計 50 ファイル
- 各書籍は `book_id` の安定ハッシュ (`SHA1(book_id) % 49 + 1`) で 1〜49 の
  ボリュームへ固定割り当て。再実行しても割り当ては変わりません (追記のみ)。
- マスタ (`01_books` + `02_highlights`) は **読むだけ**、書き換えません。

ファイル名は固定です (拡張子なし):

- ボリューム: `k2n_vol_01` 〜 `k2n_vol_49`
- 索引: `k2n_index`
- プレフィックス `k2n` は `--prefix` で変更可能

各シートの 1 枚目の列構成:

- ボリューム: `book_id, book_title, highlight_id, location, content`
  (1 冊 1 ファイルだった頃の 3 列から `book_id` / `book_title` を追加。
  1 ファイルに複数冊が混在しても、各行が自分の書籍を自己記述するため、
  NotebookLM が別の本のハイライトと取り違えません)
- 索引: `book_id, title, volume, highlight_count, last_synced_at`
  (`volume` はその本が入っているボリュームのファイル名。本 → ファイルを引けます)

ボリューム / 索引はいずれも毎回マスタからフル再生成されます (idempotent)。

##### 制限事項: Service Account では新規ファイルを作成できない

Google の Service Account は **個人 Drive 容量を 0 byte しか持たない**ため、
"My Drive" 配下に新しいスプレッドシートを所有できません
(`storageQuotaExceeded` エラーになります)。
そのため本スクリプトは **ファイル作成を行わず、既存ファイルへの書き込みのみ** を行います。
ただし固定 50 ファイル構成なので、**最初に一度だけ** 50 個を手動作成すれば、
以降は新刊が増えても新しいファイルを作る必要はありません。

##### 推奨ワークフロー

1. **親フォルダを準備する**
   - Google Drive にフォルダを 1 つ作成 (例: `kindle2notion`)
   - そのフォルダを Service Account のメールアドレスに **編集者権限** で共有
   - フォルダの URL `https://drive.google.com/drive/folders/<FOLDER_ID>` から `<FOLDER_ID>` をメモ
   - フォルダ内に `notebooklm` サブフォルダを 1 つ作成

2. **必要なファイル名一覧を取得 (dry-run)**

   ```bash
   python -m scripts.split_per_book --parent-folder <FOLDER_ID>
   ```

   `[create ]` 行と末尾のブロックに、作成すべき 50 個のファイル名が表示されます。

3. **固定 50 個の空 Google Sheets を `notebooklm/` 内に一度だけ手動作成**
   - 表示されたファイル名 (`k2n_index`, `k2n_vol_01`〜`k2n_vol_49`) と **完全一致** させる (拡張子なし)
   - 親フォルダ経由で Service Account からも編集可能になっているはず

4. **書き込み (apply)**

   ```bash
   python -m scripts.split_per_book --apply --parent-folder <FOLDER_ID>
   ```

   50 ファイルすべてが上書きされます (`[summary] update=50 missing=0`)。
   新しい書籍を追加したら `--apply` を再実行するだけで、該当ボリュームと
   索引に差分が反映されます。**ファイルの追加作成は不要**です。

実行後、Drive 上の `notebooklm/` 内の 50 個のスプレッドシートを NotebookLM に
ソースとして取り込めば OK です。

> 旧構成 (`per_book/` 内の `BK-XXXXXX__<書名>` という 1 冊 1 ファイル) を使っていた
> 場合、それらは本スクリプトでは自動削除されません。NotebookLM 側のソースを
> 新しい 50 ファイルへ差し替えたうえで、旧 `per_book/` 内のファイルは手動で
> 整理してください。

##### 補足: `--parent-folder` を省略した場合

マスタスプレッドシートが Drive 上のフォルダ内にある場合は `--parent-folder` を
省略でき、その場合は Drive API がマスタの親フォルダを自動取得します。
マスタが "My Drive" 直下にあると親フォルダを取得できないため、
明示的に `--parent-folder` を渡してください。

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