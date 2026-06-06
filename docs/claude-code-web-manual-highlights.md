# Claude Code（web）から手動ハイライトを追加するための設定

Kindle にない本（紙の本・図書館・PDF・他ストア）のハイライトを、Claude Code on
the web のチャットから Notion / Google Sheets に追加できるようにするための設定
ガイド。書き込みは `scripts/add_manual_highlights.py` が行う（Kindle スクレイパー
とは無関係。`storage_state.json` も使わない）。

> Kindle 本体の同期（`python main.py`）はブラウザ＋2FA が必要なため、web では
> なくローカルで実行する。web 環境は **手動ハイライト専用**と割り切る。

## 全体像（3 要素）

1. **シークレット（環境変数）** — web 環境に登録する
2. **ネットワークポリシー** — Notion / Google API への外向き通信を許可する
3. **依存の自動インストール** — `.claude/hooks/session-start.sh`（リポジトリ済み）

3 はコミット済みなので、ユーザーが行うのは 1 と 2 の一度きりの設定だけ。
（環境設定は「環境」に保存される。毎セッション消えるのはコンテナの中身＝依存
パッケージだけで、それはフックが自動で入れ直す。）

## 1. シークレット（環境変数）

Claude Code on the web の環境設定で、以下を環境変数として登録する。
`config/KEYS.env` は web には無くてよい（コードは実環境変数を直接読む）。

| 変数 | 必要性 | メモ |
|------|--------|------|
| `NOTION_API_KEY` | 必須 | Notion インテグレーションのトークン |
| `NOTION_DATABASE_ID` | 必須 | 書き込み先 DB の ID |
| `AMAZON_EMAIL` | 必須（検証通過用） | **手動ハイライトでは未使用**。`x@example.com` 等のダミーで可 |
| `AMAZON_PASSWORD` | 必須（検証通過用） | 同上。ダミーで可 |
| `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` | Sheets を使う場合 | サービスアカウント JSON を **丸ごと文字列で貼り付け**できる（`{` 始まりなら生 JSON 扱い） |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Sheets を使う場合 | スプレッドシート ID |

補足:
- `AMAZON_*` が必須なのは `main.load_config()` の検証によるもの。手動ハイライト
  経路では実際には使われないのでダミーで問題ない。
- Google Sheets を使わない場合は `GOOGLE_SHEETS_*` を未設定にする（Notion のみに
  書き込まれる）。両方のうち片方だけ設定するとエラーになるので、使うなら両方。

## 2. ネットワークポリシー

web 環境の外向き通信は環境のネットワークポリシーで制御される。以下のホストへの
通信を許可するポリシーを選ぶ（制限が強いと書き込み時に弾かれる）:

- `api.notion.com` … Notion
- `sheets.googleapis.com` / `www.googleapis.com` / `oauth2.googleapis.com` … Google Sheets

参考: https://code.claude.com/docs/en/claude-code-on-the-web

## 3. 依存の自動インストール（設定不要・コミット済み）

`.claude/settings.json` の SessionStart フックが `.claude/hooks/session-start.sh`
を呼び、`requirements/requirements.txt` を web セッション開始時にインストールする。
冪等（既に入っていればスキップ）かつ web 専用（`CLAUDE_CODE_REMOTE=true` のときだけ
実行）。

## 使い方（設定後）

チャットで「この本のハイライト追加して」と頼むだけ。スキル
`.claude/skills/adding-manual-highlights/` のフローで進む:

1. タイトルとハイライトを聞き取り
2. `--list-books --matches-only --title "..."` で既存本と照合し「これじゃね？」を提案
3. JSON を作って dry-run（プレビュー）を表示・確認
4. 確認後に `--apply` で Notion / Sheets へ書き込み

手動実行する場合:

```bash
# 照合（読み取りのみ）
python -m scripts.add_manual_highlights --list-books --matches-only --title "本のタイトル"

# プレビュー（書き込みなし）
python -m scripts.add_manual_highlights --input manual_highlights_input.json

# 実書き込み
python -m scripts.add_manual_highlights --input manual_highlights_input.json --apply
```

## トラブルシュート

- `Missing required environment variables ...` → 1 の必須変数（特に `AMAZON_*` の
  ダミー）が未設定。
- `--list-books` が「Google Sheets not configured」で終了 → `GOOGLE_SHEETS_*` 未設定。
  照合をスキップし、タイトルの綴りをユーザーに直接確認すればよい。
- 書き込みがタイムアウト／接続エラー → 2 のネットワークポリシーで対象ホストが
  許可されているか確認。
