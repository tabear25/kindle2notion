# Render へのデプロイ (Docker)

kindle2notion の Web UI を [Render](https://render.com) 上の Docker Web Service として公開する手順です。
VPS 版 (`deploy/README.md`) よりも手順が少なく、サーバー管理 (OS 更新・証明書更新など) も不要です。

## 仕組み

```
スマホ / PC ──HTTPS──▶ Render (xxxx.onrender.com)
                        │
                        ▼
              ┌─ Docker コンテナ ──────────────┐
              │  python web_main.py            │
              │   └ Flask (0.0.0.0:$PORT)      │
              │   └ Playwright + Chromium      │
              │  Basic 認証 (WEB_USERNAME/...)  │
              └────────────────────────────────┘
```

Render は GitHub リポジトリの `Dockerfile` をビルドしてコンテナを起動します。
`render.yaml` (Blueprint) を使うと、サービス作成と環境変数入力をまとめて行えます。

## 前提

- このリポジトリが GitHub に push されていること (`tabear25/kindle2notion`)
- リポジトリのルートに `Dockerfile` / `.dockerignore` / `render.yaml` がコミット済みであること
- Amazon / Notion の認証情報が手元にあること
  （取得方法は `deploy/README.md` のステップ6を参照）

> **重要**: `Dockerfile` などを追加・変更したら、必ず GitHub に commit & push してから
> Render での操作に進んでください。Render は GitHub 上のコードをビルドします。

## デプロイ手順

### 方法A: Blueprint (`render.yaml`) を使う — 推奨

1. [Render](https://render.com) にアカウントを作成し、GitHub アカウントを連携します。
2. ダッシュボードで **New +** → **Blueprint** を選びます。
3. `kindle2notion` リポジトリを選択します。Render が `render.yaml` を読み込みます。
4. `sync: false` の環境変数（下表）の入力を求められるので、値を入力します。
5. **Apply** を押すとビルドが始まります（初回は Chromium のインストールで 10〜15 分ほど）。
6. 完了後、`https://kindle2notion-xxxx.onrender.com` でアクセスできます。

### 方法B: 手動で Web Service を作成する

1. **New +** → **Web Service** → リポジトリ `kindle2notion` を選択。
2. 設定:
   - **Language / Runtime**: `Docker`
   - **Region**: `Singapore`（日本から最寄り）
   - **Branch**: `main`
   - **Instance Type**: `Free`（動作確認用）
   - **Health Check Path**: `/healthz`
3. **Environment** タブで下表の環境変数を追加。
4. **Create Web Service** でビルド開始。

## 環境変数

| 変数名 | 必須 | 説明 |
|---|---|---|
| `AMAZON_EMAIL` | ✅ | Amazon のメールアドレス |
| `AMAZON_PASSWORD` | ✅ | Amazon のパスワード |
| `NOTION_API_KEY` | ✅ | Notion インテグレーションのシークレット |
| `NOTION_DATABASE_ID` | ✅ | 保存先 Notion データベースの ID |
| `WEB_USERNAME` | ⭐ 強く推奨 | Web UI のログイン ID |
| `WEB_PASSWORD` | ⭐ 強く推奨 | Web UI のログインパスワード |
| `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` | 任意 | サービスアカウント JSON（**文字列そのものを貼り付け**） |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | 任意 | Sheets 有効化のゲート＋フォルダ解決の予備（旧マスタ ID でも可） |
| `NOTEBOOKLM_PARENT_FOLDER_ID` | 任意 | NotebookLM 50 ファイルを置いた Drive フォルダ ID。Sheets 同期の主な参照先（旧マスタ廃止後はこれが必須級） |
| `STORAGE_STATE_PATH` | 任意 | セッション保存先（永続ディスク利用時のみ設定） |

> **⚠️ `WEB_USERNAME` / `WEB_PASSWORD` は必ず設定してください。**
> 設定しないと URL を知っている誰でもあなたの Amazon アカウントでスクレイピングを
> 実行できてしまいます。

> Google Sheets を使う場合、Render にはサービスアカウントの JSON ファイルを置けないため、
> `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` には **JSON ファイルの中身（`{` で始まる文字列）
> をそのまま** 貼り付けてください。コードは `{` で始まる値を JSON 文字列として扱います。

> `PORT` は Render が自動で設定するため、自分で設定する必要はありません
> （`web_main.py` が `PORT` を読むよう修正済み）。

## 無料プランの注意点

| 項目 | 内容 |
|---|---|
| スリープ | 15 分アクセスが無いとコンテナ停止。次アクセス時に起動待ち（数十秒〜1分） |
| ディスク非永続 | コンテナ再起動で `storage_state.json` が消える → **起動のたびに 2FA ログインが必要** |
| メモリ | 512MB。書籍数が多いと Chromium がメモリ不足で落ちることがある（その場合は上位プランへ） |
| ビルド時間 | 初回は Chromium インストールで 10〜15 分 |

## セッションを永続化する（有料プラン）

`storage_state.json` を永続化すると 2FA ログインの頻度を減らせます。
**永続ディスクを付けると無料プランは使えなくなります**（Starter プラン以上が必要）。

1. `render.yaml` の `plan: free` を `plan: starter` に変更。
2. `render.yaml` 末尾の `disk:` ブロックのコメントアウトを外す。
3. 環境変数を追加:
   - `STORAGE_STATE_PATH` = `/var/data/storage_state.json`
4. commit & push → Render が再デプロイ。

これで Amazon セッションがディスク `/var/data` に保存され、
再起動・再デプロイをまたいで保持されます。

## 動作確認

- `https://<サービス名>.onrender.com/healthz` → `{"status":"ok"}` が返ればサーバー稼働中。
- `https://<サービス名>.onrender.com/` → Basic 認証後に Web UI が表示される。

## トラブルシューティング

**ビルドは成功するが起動しない / ヘルスチェックが失敗する**
- Render はポート `$PORT` で待ち受けます。`web_main.py` は `PORT` を読むよう修正済みです。
- Render ダッシュボードの **Logs** で例外内容を確認してください。

**スクレイピング実行時に Chromium が起動しない**
- `Dockerfile` で `playwright install --with-deps chromium` 済み、`--no-sandbox` 付きで
  起動するよう `main.py` を修正済みです。それでも落ちる場合はメモリ不足の可能性 → 上位プランへ。

**処理の途中でコンテナが再起動する / メモリ不足になる**
- 無料・Starter プランは 512MB です。一度に処理する書籍数を減らすか、上位プランを検討してください。

**毎回 2FA を求められる**
- 無料プランの仕様です（ディスク非永続）。上記「セッションを永続化する」を参照してください。
