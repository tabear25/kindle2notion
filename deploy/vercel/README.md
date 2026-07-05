# Vercel デプロイガイド（フロントエンド）

`frontend/` ディレクトリ（index.html + static/）を Vercel の静的ホスティングでそのまま配信します。
ビルド工程はなく、**ローカルに Node.js は不要**です。すべて Vercel のダッシュボードだけで完了します。

構成:

```
スマホ/PC → Vercel (frontend/ 静的UI) → Render (Flask API + Playwright) → Turso / Notion / Sheets
```

フロントは常時起動の Vercel から即表示され、バックエンド（Render 無料プラン）が
スリープしていても「起動中...」バナーを出しながら自動で起こします。

## 前提

- バックエンドが Render にデプロイ済みで、URL（例: `https://kindle2notion.onrender.com`）が分かること
- Render 側に `WEB_USERNAME` / `WEB_PASSWORD`（Basic 認証）が設定済みであること
  （フロントを公開インターネットに置くため、Basic 認証は必ず設定してください）

## 手順

### 1. Vercel プロジェクトを作る

1. https://vercel.com にログイン（GitHub アカウント連携）
2. **Add New... → Project** → このリポジトリ（`kindle2notion`）を Import
3. 設定画面で次の 3 点だけ変更する:
   - **Root Directory**: `frontend` （Edit を押して選択）
   - **Framework Preset**: `Other`
   - **Build Command / Output Directory**: 空欄のまま（静的配信）
4. **Deploy** を押す

以後、GitHub の `main` に push するたびに自動で再デプロイされます。

### 2. Render 側に CORS を設定する

Vercel の URL（例: `https://kindle2notion.vercel.app`）を、Render の環境変数に設定します。

```
CORS_ALLOWED_ORIGINS=https://kindle2notion.vercel.app
```

- 完全一致で照合されます（末尾スラッシュ不要）
- プレビューデプロイも使う場合はカンマ区切りで追加できます

### 3. スマホから接続設定をする（初回のみ）

1. スマホで Vercel の URL を開く
2. 開始画面下部の **「接続設定（別サーバーのバックエンドを使う場合）」** を開く
3. 次を入力して保存:
   - バックエンド URL: `https://<あなたのサービス名>.onrender.com`
   - Basic 認証ユーザー名 / パスワード: Render に設定した `WEB_USERNAME` / `WEB_PASSWORD`
4. 「バックエンドに接続できました。」と表示されれば完了

設定はブラウザの localStorage に保存されるため、次回以降の入力は不要です。

## 動作の補足

- バックエンドがスリープ中は「バックエンドを起動中です（最大1分）」と表示され、
  `/healthz` への 5 秒間隔のポーリングがそのままウェイクアップを兼ねます
- 進行状況（SSE）は fetch ストリームで受信します（Basic 認証ヘッダー付き）。
  切断時は 2 秒後に自動再接続し、サーバーが全イベントを再送するため取りこぼしません
- Render 単体でも同じ UI が同一オリジンで動くので、Vercel は「常時起動の入り口」という位置づけです

## トラブルシューティング

| 症状 | 原因と対処 |
| --- | --- |
| ブラウザのコンソールに CORS エラー | `CORS_ALLOWED_ORIGINS` の値が Vercel の URL と完全一致しているか確認（`https://` から、末尾スラッシュなし） |
| 401 Unauthorized | 接続設定のユーザー名/パスワードが Render の `WEB_USERNAME` / `WEB_PASSWORD` と一致しているか確認 |
| 「バックエンドを起動中です」が数分続く | Render のダッシュボードでサービスが落ちていないか・ビルド失敗していないかを確認 |
