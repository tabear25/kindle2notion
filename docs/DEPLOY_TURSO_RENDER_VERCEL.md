# デプロイ手順書 — Turso + Render + Vercel（この1枚で完結）

作成: 2026-07-05。コードは main にマージ・push・実機検証済みです。
**残っている作業はダッシュボード操作だけ（合計15分ほど＋Render初回ビルド待ち10〜15分）**。
この文書の STEP 0 → 4 を上から順にやれば完成します。

---

## 完成形（新アーキテクチャ）

```
スマホ/PC → Vercel（frontend/ 静的UI・常時起動）
                │  fetch + Basic認証（SSEもfetchで受信）
                ▼
            Render（Flask + gunicorn + Chromium, Docker）
                ├→ Turso（Amazonセッション / Notion重複キャッシュ / 実行履歴）
                ├→ Notion（ハイライト保存先）
                └→ Google Drive の NotebookLM 50ファイル（k2n_index + k2n_vol_01..49）
                     ※旧マスタ（01_books/02_highlights）は退役済み・更新されません
```

この構成のポイント:

- **Turso のおかげで、Render 無料プランの弱点だった「再起動ごとの 2FA 再ログイン」が消えます**（有料ディスク不要）。
- `TURSO_*` 未設定ならローカル SQLite（`local_store.db`）に自動フォールバックするので、いつもの `py -3 main.py`（GUI）もそのまま動きます。
- Vercel は「常時起動の入り口」。Render が寝ていても「起動中…」バナーを出しながら自動で起こします。

---

## 事前に手元に用意するもの

| もの | 用途 |
| --- | --- |
| GitHub アカウント | Render / Vercel / Turso すべて GitHub 連携でサインアップできる |
| `config/KEYS.env` の中身 | Render の環境変数へコピーする元ネタ |
| スマホ | STEP 4 の接続設定（1回だけ） |

---

## STEP 0: ローカルで最終確認（5分・任意だが推奨）

```powershell
# 1) 2回連続で実行 → 2回目はブラウザウィンドウが出ず、数秒で取得が始まればOK
py -3 main.py
py -3 main.py

# 2) XHR/DOM 両モードの出力一致と速度差の確認（5冊だけ）
py -3 -m test.compare_scrape_modes 5

# 3) テスト全緑の確認
py -3 -m pytest test/ --basetemp=.pytest_tmp
```

---

## STEP 1: Turso（5分・無料）

1. https://app.turso.tech を開き、GitHub でサインアップ
2. **Create Database** → 名前は `kindle2notion`、リージョンは **Tokyo (NRT)**
3. データベースの URL（`libsql://xxxx.turso.io`）をコピー → これが `TURSO_DATABASE_URL`
4. データベース設定画面で **Create Token** → コピー → これが `TURSO_AUTH_TOKEN`
5. **【重要・おすすめ】** ローカルの `config/KEYS.env` にも上の2行を追記して、`py -3 main.py` を1回実行する
   → 手元の Amazon セッションが Turso にミラーされるため、**Render 側では 2FA を一度も入力せずに済みます**

テーブルはアプリが初回アクセス時に自動作成します（マイグレーション作業なし）。

---

## STEP 2: Render（入力5分＋初回ビルド10〜15分）

1. https://render.com を開き、GitHub 連携でサインアップ
2. **New +** → **Blueprint** → リポジトリ `tabear25/kindle2notion` を選択（`render.yaml` を自動で読み込みます）
3. 環境変数の入力を求められるので、下表のとおり入力（ほとんどはローカルの `config/KEYS.env` からコピー）

| 環境変数 | 入れる値 |
| --- | --- |
| `AMAZON_EMAIL` / `AMAZON_PASSWORD` | KEYS.env の値をそのまま |
| `NOTION_API_KEY` / `NOTION_DATABASE_ID` | KEYS.env の値をそのまま |
| `WEB_USERNAME` / `WEB_PASSWORD` | **ここで新しく決める**（Web UI のログイン。公開URLになるので必須） |
| `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` | STEP 1 で取得した値 |
| `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` | サービスアカウント **JSONファイルの中身を丸ごと貼り付け**（`{` で始まる文字列。パスではない点に注意） |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | KEYS.env の値をそのまま（Sheets 有効化のゲート） |
| `NOTEBOOKLM_PARENT_FOLDER_ID` | KEYS.env の値をそのまま（**k2n の50ファイルがある Drive フォルダ ID。これが無いと k2n に書けません**） |
| `CORS_ALLOWED_ORIGINS` | **いったん空欄**（STEP 4 で Vercel の URL を入れる） |

4. **Apply** → ビルド開始（初回は Chromium インストールで 10〜15 分。放置でOK）
5. 完了したら確認: `https://<サービス名>.onrender.com/healthz` → `{"status":"ok"}` が返ればOK

> つまずいたら詳細版: [`deploy/render/README.md`](../deploy/render/README.md)

---

## STEP 3: Vercel（3分）

1. https://vercel.com を開き、GitHub 連携でサインアップ
2. **Add New... → Project** → `kindle2notion` を **Import**
3. 設定はこの3点**だけ**変更:
   - **Root Directory**: `frontend`（Edit を押して選択）
   - **Framework Preset**: `Other`
   - **Build Command / Output Directory**: 空欄のまま（静的配信・ビルドなし）
4. **Deploy** → 完了後の URL（`https://xxxx.vercel.app`）を控える

以後、GitHub の main に push するたびに Render / Vercel とも自動で再デプロイされます。

> つまずいたら詳細版: [`deploy/vercel/README.md`](../deploy/vercel/README.md)

---

## STEP 4: つなぎ込み（2分）

1. Render のダッシュボード → 対象サービス → **Environment** →
   `CORS_ALLOWED_ORIGINS` = `https://xxxx.vercel.app`（STEP 3 の URL。**末尾スラッシュなし・完全一致**）
   → 保存すると自動で再起動します
2. スマホで Vercel の URL を開く →
   開始画面下部の **「接続設定（別サーバーのバックエンドを使う場合）」** を開き、
   - バックエンド URL: `https://<サービス名>.onrender.com`
   - Basic 認証: STEP 2 で決めた `WEB_USERNAME` / `WEB_PASSWORD`
   を入力して保存（1回だけ。ブラウザに記憶されます）

「バックエンドに接続できました。」と出たら完成です。

---

## 最終動作確認チェックリスト

- [ ] スマホで Vercel を開く → （Render が寝ていれば）起動中バナー → 「接続できました」
- [ ] 「同期を開始」（最初は書籍数 `1` で試すと早い）→ 進捗バーが動き完了画面まで到達
- [ ] 2FA を聞かれない（STEP 1-5 を実施した場合）。聞かれた場合も**その1回だけ**で、以後は不要になる
- [ ] Notion に重複ページが増えていない
- [ ] 該当する `k2n_vol_XX` に新規ハイライト、`k2n_index` の `last_synced_at` が更新されている
- [ ] Render を **Manual Deploy**（再起動）→ もう一度同期しても 2FA 不要（Turso 復元の確認）
- [ ] 「紙の本のハイライトを手動で追加」も一連（検索 → 内容を確認 → 追加）動く

---

## 挙動が変わっている点（実装・検証済み）

1. **Notion で手動削除したページは復活しません**（以前は次回同期で復活していました）。
   復活させたい時: UI の「Notion キャッシュを全再同期」チェック、または `py -3 -m scripts.resync_notion_cache`
2. GUI（`py -3 main.py`）はセッション有効時ブラウザウィンドウが出ません（ログインが必要な時だけ表示）
3. ハイライトの多い本は従来より**多く**取れることがあります（旧方式の取りこぼし解消。重複はしません）
4. スプレッドシートの保存先は **k2n_index + k2n_vol_\* に一本化**。旧マスタ（`01_books` / `02_highlights`）は更新停止（読み取り専用で残置）

---

## 困ったら（症状 → 対処）

| 症状 | 対処 |
| --- | --- |
| ブラウザのコンソールに CORS エラー | `CORS_ALLOWED_ORIGINS` が Vercel の URL と完全一致か確認（`https://` から、末尾スラッシュなし） |
| 401 Unauthorized | 接続設定のユーザー名/パスワードが Render の `WEB_USERNAME` / `WEB_PASSWORD` と一致しているか |
| 「起動中です」が数分続く | Render のダッシュボードでビルド失敗・クラッシュがないか Logs を確認 |
| 毎回 2FA を聞かれる | `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` の設定漏れ・タイプミス。Logs に `Warning: operational store unavailable` が出ていないか |
| k2n に反映されない | `NOTEBOOKLM_PARENT_FOLDER_ID` の設定漏れが典型。完了ログ/実行履歴の `missing_files` に何か出ていないか |
| 処理が遅い・止まる | `https://<サービス名>.onrender.com/api/runs` で直近の実行記録（scrape_mode / 件数 / エラー）を確認。`SCRAPE_MODE=dom` で旧方式に切替可 |
| メモリ不足で落ちる | 無料プランは512MB。一度に処理する書籍数を減らすか上位プランへ |

---

## 運用メモ

- 実行履歴: `GET /api/runs`（直近20件。どのモードで何件書いたかが分かる）
- 環境変数の全既定値: `SCRAPE_MODE=xhr` / `NOTION_DEDUP_MODE=cache` / `GUNICORN_THREADS=8` / `K2N_LOCAL_DB_PATH=local_store.db`
- ローカル GUI・Render は Turso 経由で**同じ Amazon セッションを共有**します（新しい方が優先されるので衝突しません）
- VPS の旧構成は休止中（GitHub Actions のデプロイは手動実行のみに変更済み）
