# 外出先からアクセスする (VPS デプロイ)

自宅の Wi-Fi 外からでもスマホで Web UI を操作できるようにするための構成と手順です。  
無料枠のクラウド VPS 上で Flask を常駐させ、Caddy (自動 HTTPS) + DuckDNS (無料サブドメイン) 経由で公開し、GitHub Actions で自動デプロイします。

## 構成

```
スマホ ──HTTPS──▶ DuckDNS サブドメイン
                 │
                 ▼
        ┌────────── VPS (Ubuntu 24.04) ──────────┐
        │  Caddy 80/443 ─▶ Flask 127.0.0.1:5000  │
        │         ↑ Let's Encrypt 自動更新        │
        │  systemd: kindle2notion-web.service    │
        │    └─ python web_main.py               │
        │                                        │
        │  Basic 認証 (WEB_USERNAME / PASSWORD)   │
        │  ufw: 22 / 80 / 443 のみ                │
        └────────────────────────────────────────┘
                 ▲
                 │ GitHub Actions (push → SSH → git pull + restart)
        GitHub  ─┘
```

## 手動で行う必要がある設定

このデプロイでは、以下の 8 項目はユーザー自身による手動操作が必要です。セットアップ開始前にすべて準備することを推奨します。

### 1. クラウド VPS のアカウント作成とインスタンス起動

- [Oracle Cloud Always Free (Ampere A1)](https://www.oracle.com/cloud/free/) — 推奨 (1-4 vCPU / 最大 24 GB RAM が無期限無料)
- または [GCP e2-micro Always Free](https://cloud.google.com/free) (1 vCPU / 1 GB RAM)
- OS は **Ubuntu 24.04 LTS** を選択
- パブリック IP アドレスをメモしておく

### 2. DuckDNS のサブドメイン取得

- https://www.duckdns.org/ に GitHub / Google / Twitter などのアカウントでログイン
- 任意のサブドメインを登録 (例: `kindle2notion-yourname.duckdns.org`)
- トップページに表示される **トークン** (`xxxxxxxx-xxxx-...`) をメモ

### 3. SSH 鍵ペアの生成と VPS への登録

```bash
ssh-keygen -t ed25519 -f ~/.ssh/kindle2notion_vps -C "kindle2notion-deploy"
ssh-copy-id -i ~/.ssh/kindle2notion_vps.pub <USER>@<VPS_IP>
```

VPS 側で `/etc/ssh/sshd_config` を編集し、次を無効化:

- `PasswordAuthentication no`
- `PermitRootLogin no`

### 4. VPS 上での初回セットアップ

```bash
sudo git clone https://github.com/tabear25/kindle2notion.git /opt/kindle2notion
sudo bash /opt/kindle2notion/deploy/setup.sh
```

セットアップ後に、下記を自分の環境に合わせて書き換え:

```bash
# DuckDNS トークンとサブドメイン名を配置
echo "<YOUR_DUCKDNS_TOKEN>"   | sudo tee /etc/duckdns/token  >/dev/null
echo "kindle2notion-yourname" | sudo tee /etc/duckdns/domain >/dev/null
sudo chmod 600 /etc/duckdns/token /etc/duckdns/domain

# Caddyfile のドメイン名を書き換え
sudo sed -i 's/kindle2notion-xxx.duckdns.org/kindle2notion-yourname.duckdns.org/' /etc/caddy/Caddyfile

# DuckDNS 初回更新 → Caddy 起動
sudo /usr/local/bin/duckdns-update
sudo systemctl restart caddy
```

### 5. `config/KEYS.env` の作成 (VPS 上のみ、Git には含めない)

`/opt/kindle2notion/config/KEYS.env` を作成:

```env
AMAZON_EMAIL=<your amazon email>
AMAZON_PASSWORD=<your amazon password>

NOTION_API_KEY=<your notion integration secret>
NOTION_DATABASE_ID=<your database id>

# 任意: Google Sheets を使う場合
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=/opt/kindle2notion/config/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=<your spreadsheet id>
GOOGLE_SHEETS_WORKSHEET_NAME=Sheet1

# 必須: 外部公開時の Basic 認証
WEB_USERNAME=<好きなユーザー名>
WEB_PASSWORD=<openssl rand -base64 32 などで生成した長いパスワード>
```

ファイル権限を絞っておく:

```bash
sudo chown kindle2notion:kindle2notion /opt/kindle2notion/config/KEYS.env
sudo chmod 600 /opt/kindle2notion/config/KEYS.env
```

### 6. Notion / Amazon / Google シートの各種資格情報の取得

メインの `README.md` (リポジトリルート) の「セットアップ」を参照:

- Notion Integration の作成とデータベース共有
- Amazon の Kindle Notebook にアクセス可能なアカウント
- (任意) Google Cloud の Service Account + JSON 鍵

### 7. GitHub リポジトリの Secrets 登録

リポジトリの **Settings → Secrets and variables → Actions** に以下を登録:

| Secret 名 | 値 |
|-----------|-----|
| `VPS_HOST` | VPS の IP または DuckDNS ドメイン |
| `VPS_USER` | SSH ログインに使う VPS 上のユーザー名 |
| `VPS_SSH_KEY` | 手順 3 で生成した **秘密鍵** `~/.ssh/kindle2notion_vps` の中身全部 |
| `VPS_PORT` | (任意) SSH ポート。省略時は 22 |

### 8. 初回動作確認

```bash
sudo systemctl start kindle2notion-web
sudo systemctl status kindle2notion-web
```

- スマホを **モバイル回線 (4G/5G)** に切り替え、自宅 Wi-Fi を切る
- ブラウザで `https://kindle2notion-yourname.duckdns.org/` を開く
- Basic 認証 (手順 5 の `WEB_USERNAME` / `WEB_PASSWORD`) でログインできること
- パイプラインを 1 回走らせ、2 段階認証コード入力まで問題なく動くこと

## 自動デプロイの流れ

`main` ブランチへの push をトリガに `.github/workflows/deploy.yml` が起動し、VPS へ SSH して以下を実行します。

```bash
cd /opt/kindle2notion
git fetch --all
git reset --hard origin/main
.venv/bin/pip install -r requirements/requirements.txt
sudo systemctl restart kindle2notion-web
```

## トラブルシュート

### Caddy が証明書を取得できない

- DuckDNS の A レコードが VPS の IP を指しているか: `dig +short kindle2notion-yourname.duckdns.org`
- 80 番 / 443 番が ufw で開いているか: `sudo ufw status`
- ログ: `sudo journalctl -u caddy -n 200`

### SSE (/api/events) の進捗が途中で止まる

- `Caddyfile` の `flush_interval -1` が設定されているか確認
- 間に別のリバースプロキシ (Cloudflare proxy など) を挟む場合は streaming / buffering 設定も要調整

### Playwright が起動しない

```bash
sudo -u kindle2notion /opt/kindle2notion/.venv/bin/python -m playwright install chromium
sudo /opt/kindle2notion/.venv/bin/python -m playwright install-deps chromium
```

### systemd でログを見る

```bash
sudo journalctl -u kindle2notion-web -f
```
