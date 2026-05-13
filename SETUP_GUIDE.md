# kindle2notion セットアップガイド（Windows + 初心者向け / 完全版）

このガイドは「**ゼロから、スマホで `https://〜.duckdns.org` を開いて Kindle ハイライトを Notion に保存できる状態**」まで到達するためのワンストップ手順書です。  
所要時間 **約 60 分**。コピペ中心で進められます。

> 対象環境
> - 手元 PC: **Windows 10 / 11**（PowerShell または Windows Terminal）
> - サーバー: **Oracle Cloud の無料 VPS（Ubuntu 24.04 LTS）** を立てます
> - その他: Notion / Amazon / DuckDNS / GitHub のアカウント（すべて無料）

---

## 目次

- [0. なぜ「今は動いていない」のか（30秒で理解）](#0-なぜ今は動いていないのか30秒で理解)
- [1. 現状診断フローチャート](#1-現状診断フローチャート)
- [2. Windows ターミナルの事前チェック](#2-windows-ターミナルの事前チェック)
- [3. 準備チェックリスト](#3-準備チェックリスト)
- [4. 第1部: 鍵と住所を取る（アカウント設定）](#4-第1部-鍵と住所を取るアカウント設定)
- [5. 第2部: VPS にログインして自動セットアップ](#5-第2部-vps-にログインして自動セットアップ)
- [6. 第3部: 起動 と スマホでアクセス確認](#6-第3部-起動-と-スマホでアクセス確認)
- [7. 第4部: 動かないときの自己診断（トラブルシュート）](#7-第4部-動かないときの自己診断トラブルシュート)
- [8. 付録A: 自宅 Wi-Fi 内だけで動かしたい場合（Windows ローカル実行）](#8-付録a-自宅-wi-fi-内だけで動かしたい場合windows-ローカル実行)
- [9. 付録B: 今後の運用（GitHub に push → 自動デプロイ）](#9-付録b-今後の運用github-に-push--自動デプロイ)
- [10. 用語集](#10-用語集)

---

## 0. なぜ「今は動いていない」のか（30秒で理解）

`kindle2notion` は **Web サーバーを自分で起動して、はじめて URL からアクセスできる** タイプのツールです。GitHub にコードを置いただけでは URL にアクセスしてもつながりません。

```
[あなたのスマホ] ──HTTPS──▶ [ DuckDNS のドメイン ]
                                  │
                                  ▼
                  ┌──── インターネット上の VPS（24時間稼働） ────┐
                  │  Caddy ─▶ Flask(Python) ─▶ Notion API     │
                  │     ↑                                     │
                  │     HTTPS 自動更新                         │
                  └──────────────────────────────────────────┘
```

つまり、URL からどこからでもアクセスしたい場合に必要なのは:
1. **24 時間動き続けるサーバー（VPS）**
2. **覚えやすい住所（DuckDNS のドメイン）**
3. **HTTPS で安全に通信（Caddy）**
4. **アプリ本体を常駐させる仕組み（systemd）**

このガイドはこの 4 つを順番に組み立てていきます。

---

## 1. 現状診断フローチャート

「設定はした、でも動かない」場合、まず自分の現在地を確認してください。

```
Q1. Oracle Cloud で VPS を起動した？
   └─ No  → 第1部 ステップ 4.4 へ
   └─ Yes ↓
Q2. Windows ターミナルから ssh で VPS にログインできる？
   └─ No  → 第2部 ステップ 5.1〜5.4 へ
   └─ Yes ↓
Q3. VPS の中で `systemctl status kindle2notion-web` が active (running) になっている？
   └─ No  → 第3部 ステップ 6.1 へ
   └─ Yes ↓
Q4. スマホ（モバイル回線）で https://〜.duckdns.org/ を開ける？
   └─ No  → 第4部「症状別トラブルシュート」へ
   └─ Yes ↓
Q5. Basic 認証は通るけど画面が真っ白 or 進捗が止まる？
   └─ Yes → 第4部「進捗が止まる」へ
   └─ No  → 完成 🎉
```

---

## 2. Windows ターミナルの事前チェック

ここを通過してから先に進むと、後でハマりません。

### 2.1 「Windows ターミナル」を起動する

スタートメニューで **「terminal」** または **「powershell」** と入力 → 表示されたアプリを起動します。  
（Windows 11 なら「ターミナル」、Windows 10 なら「Windows PowerShell」でOK）

> ⚠ **「コマンドプロンプト (cmd.exe)」は使いません。** 必ず PowerShell を開いてください。

### 2.2 必須コマンドが入っているか確認

下のコマンドを **1行ずつコピペ** して Enter。期待値どおりに表示されればOKです。

```powershell
# PowerShell のバージョン（5.1 以上ならOK）
$PSVersionTable.PSVersion
```

```powershell
# OpenSSH クライアント（VPS に接続するために必須）
ssh -V
```
✓ `OpenSSH_for_Windows_x.x ...` のような表示になればOK  
× `用語 'ssh' は ... 認識されません` と出たら → 「設定」アプリ → 「アプリ」 → 「オプション機能」 → 「機能の追加」 → 「**OpenSSH クライアント**」をインストールしてから PowerShell を再起動

```powershell
# SSH 鍵作成コマンド
ssh-keygen -? 2>$null; "ok"
```
✓ 最後に `ok` と出ればOK

```powershell
# インターネット疎通テスト
Test-NetConnection www.oracle.com -Port 443
```
✓ `TcpTestSucceeded : True` ならOK

これで Windows ターミナルの準備は完了です。

---

## 3. 準備チェックリスト

| 項目 | 用途 | 取得先 |
|---|---|---|
| Amazon アカウント | Kindle ハイライト取得元 | (既にお持ちのもの) |
| Notion アカウント | ハイライト保存先 | https://www.notion.so/ |
| GitHub アカウント | コード取得・DuckDNS ログインに使用 | https://github.com/ |
| Oracle Cloud アカウント | 無料 VPS を借りる | https://www.oracle.com/cloud/free/ |
| DuckDNS アカウント | 無料サブドメイン取得 | https://www.duckdns.org/ |

### メモ帳に控える情報

作業中に何度も使うので、Windows のメモ帳に最初から書き出しておきます。

```text
[ Notion ]
  NOTION_API_KEY      = ★第1部4.1で取得★
  NOTION_DATABASE_ID  = ★第1部4.2で取得★

[ Amazon ]
  AMAZON_EMAIL        = (Kindleで使っているメアド)
  AMAZON_PASSWORD     = (そのパスワード)

[ VPS ]
  VPS_IP              = ★第1部4.4で取得★
  VPS_USER            = ubuntu        ← Oracle Cloud なら固定で ubuntu

[ DuckDNS ]
  サブドメイン名       = ★第1部4.5で決める★ (例: my-kindle)
  TOKEN               = ★第1部4.5で取得★

[ Web 認証 ]
  WEB_USERNAME        = admin
  WEB_PASSWORD        = ★自分で決める。英数字記号で16文字以上推奨★
```

---

## 4. 第1部: 鍵と住所を取る（アカウント設定）

### 4.1 Notion API キーを取得

1. https://www.notion.so/profile/integrations を開く
2. 「**+ 新しいインテグレーション**」をクリック
3. 適当な名前（例: `kindle2notion`）を入れて作成
4. 表示される「**内部インテグレーションシークレット**」をコピー → メモ帳の `NOTION_API_KEY` に貼り付け

### 4.2 Notion データベースを準備して ID を取得

1. Notion で新しい **データベース（フルページ）** を作る
2. 次の 3 つのプロパティを必ず作る（**大文字小文字も完全一致**）

   | プロパティ名 | タイプ |
   |---|---|
   | `Title` | タイトル |
   | `Content` | テキスト |
   | `Page` | テキスト |

3. データベース右上の **「⋯」 → 「接続を追加」** → 4.1 で作ったインテグレーションを選ぶ  
   ⚠ **これを忘れると 404 / 401 エラー** になります（最頻出ハマりポイント）

4. データベースのページを開いた状態の URL から ID を抽出  
   `https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`  
   → `?` の前にある **32桁の英数字** が `NOTION_DATABASE_ID`。メモ帳へ。

### 4.3 Amazon の確認

特別な設定はありません。次の URL を開いて、Kindle ハイライトが見えることだけ確認してください。  
👉 https://read.amazon.co.jp/notebook

メアドとパスワードはメモ帳に控えるだけでOK。

### 4.4 Oracle Cloud で VPS を起動

1. https://www.oracle.com/cloud/free/ にアクセス → アカウント作成（クレカ登録は必要だが Always Free 枠で課金されない）
2. ログイン後、左上メニュー → 「**コンピュート**」 → 「**インスタンス**」 → 「**インスタンスの作成**」
3. 設定:
   - **イメージ**: `Canonical Ubuntu 24.04` を選択
   - **シェイプ**: 「シェイプの変更」→ **`VM.Standard.A1.Flex` (Ampere, Always Free)** → OCPU **2**、メモリ **12 GB** くらいで作成
   - **SSH キー**: いったん「SSH キーなしで続行」でもOK（後で 5.3 で公開鍵を流し込みます）  
     ※ Oracle UI で先に公開鍵を貼ってもOK。その場合 5.2〜5.3 はスキップ可
4. 作成後、インスタンス詳細画面で **「パブリック IP アドレス」** をメモ帳の `VPS_IP` に控える
5. **セキュリティリストで 80 / 443 を開ける**（重要）:
   - 左メニュー → 「ネットワーキング」 → 「仮想クラウドネットワーク」 → 該当 VCN → 「セキュリティリスト」 → デフォルトのものを開く
   - 「**イングレス・ルールの追加**」で次の 2 つを追加:
     - ソース `0.0.0.0/0`、宛先ポート `80`
     - ソース `0.0.0.0/0`、宛先ポート `443`

### 4.5 DuckDNS でサブドメインを取得

1. https://www.duckdns.org/ を開いて GitHub または Google でログイン
2. 「sub domain」欄に好きな名前（例: `my-kindle`）を入れて **add domain**
   → これで `my-kindle.duckdns.org` が自分のものになります。メモ帳へ。
3. ページ上部の **`token`**（例: `a1b2c3d4-...`）を **TOKEN** としてメモ帳へ
4. 取得したドメインの「**current IP**」欄に、4.4 でメモした `VPS_IP` を入れて **update ip** を押す

---

## 5. 第2部: VPS にログインして自動セットアップ

ここからは **手元の Windows ターミナル** と **VPS の中（SSH ログイン後）** を行き来します。コードブロックの直前にラベルを付けますので、間違えないようにしてください。

### 5.1 SSH 鍵を作る

▼ **Windows ターミナル (手元PC) で実行**
```powershell
ssh-keygen -t ed25519 -f "$HOME\.ssh\kindle2notion_vps" -C "kindle2notion-deploy"
```

- 「Enter passphrase」と聞かれたら **何も入力せず Enter を 2 回** 押す
- 完成すると `C:\Users\<あなた>\.ssh\kindle2notion_vps`（秘密鍵）と `kindle2notion_vps.pub`（公開鍵）の 2 ファイルが生まれます

### 5.2 公開鍵を VPS に渡す

Windows には `ssh-copy-id` が無いので、PowerShell のワンライナーを使います。  
**`<VPS_IP>` を 4.4 でメモした IP に書き換えて** から実行してください。

▼ **Windows ターミナル (手元PC) で実行**
```powershell
type "$HOME\.ssh\kindle2notion_vps.pub" | ssh ubuntu@<VPS_IP> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

- 初回接続時に `Are you sure you want to continue connecting? (yes/no/[fingerprint])` と聞かれたら → **`yes`** と入力して Enter
- パスワードを聞かれたら Oracle Cloud で設定した OS パスワード（無ければ Oracle のコンソール画面で `ubuntu` ユーザのパスワードを設定するか、先に Oracle UI から公開鍵を登録する）

> 💡 Oracle Cloud は標準でパスワード認証を許可していないので、**インスタンス作成時に公開鍵を貼り付ける方が早い**です。その場合は 5.2 をスキップし、5.1 で作った `kindle2notion_vps.pub` の中身（`type "$HOME\.ssh\kindle2notion_vps.pub"` で表示できます）を Oracle の「SSH キーの追加」欄に貼ってインスタンスを作り直してください。

### 5.3 VPS にログイン

▼ **Windows ターミナル (手元PC) で実行**
```powershell
ssh -i "$HOME\.ssh\kindle2notion_vps" ubuntu@<VPS_IP>
```

✓ プロンプトが `ubuntu@instance-...:~$` に変わればログイン成功。  
ここから先は **Linux (Ubuntu) のコマンド** です。パスは `/` 区切りに変わります。

### 5.4 kindle2notion をダウンロードして自動セットアップ

▼ **VPS の中 (SSH ログイン後) で実行**
```bash
sudo git clone https://github.com/tabear25/kindle2notion.git /opt/kindle2notion
sudo bash /opt/kindle2notion/deploy/setup.sh
```

文字が大量に流れますが、Python の依存パッケージ・Caddy・Playwright などが自動でインストールされます。**数分かかります**。

### 5.5 DuckDNS の情報を VPS に登録

▼ **VPS の中 で実行**（`<YOUR_DUCKDNS_TOKEN>` と `my-kindle` を **自分のもの** に書き換える）
```bash
echo "<YOUR_DUCKDNS_TOKEN>" | sudo tee /etc/duckdns/token   >/dev/null
echo "my-kindle"            | sudo tee /etc/duckdns/domain  >/dev/null
sudo chmod 600 /etc/duckdns/token /etc/duckdns/domain
sudo /usr/local/bin/duckdns-update
```

✓ 最後のコマンドが `OK` を返せば DuckDNS への IP 登録成功。

### 5.6 Caddyfile のドメインを書き換える

▼ **VPS の中 で実行**（`my-kindle` の部分だけ自分のサブドメインに書き換える）
```bash
sudo sed -i 's/kindle2notion-xxx.duckdns.org/my-kindle.duckdns.org/' /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

確認:
```bash
sudo systemctl status caddy
```
✓ `active (running)` なら成功。終了は `q` キー。

### 5.7 KEYS.env を作成（最重要）

▼ **VPS の中 で実行**
```bash
sudo nano /opt/kindle2notion/config/KEYS.env
```

nano が開いたら、次の内容を貼り付けて `< >` の部分を書き換えます:

```env
# Amazon
AMAZON_EMAIL=<あなたのAmazonメールアドレス>
AMAZON_PASSWORD=<あなたのAmazonパスワード>

# Notion
NOTION_API_KEY=<4.1で取得したシークレット>
NOTION_DATABASE_ID=<4.2で取得した32桁ID>

# Web UI 認証（外部公開時は必須）
WEB_USERNAME=admin
WEB_PASSWORD=<長くて複雑なパスワード>

# Flask は内部のみ受け付ける（Caddy 経由でアクセスする）
WEB_HOST=127.0.0.1
```

> nano の貼り付け方: PowerShell からコピーしたテキストは、SSH ターミナル内で **右クリック** すると貼り付けされます（Windows Terminal の標準動作）。

保存して閉じる: `Ctrl + O` → `Enter` → `Ctrl + X`

最後にファイル権限を引き締めます:
```bash
sudo chown kindle2notion:kindle2notion /opt/kindle2notion/config/KEYS.env
sudo chmod 600 /opt/kindle2notion/config/KEYS.env
```

---

## 6. 第3部: 起動 と スマホでアクセス確認

### 6.1 アプリを起動

▼ **VPS の中 で実行**
```bash
sudo systemctl start kindle2notion-web
sudo systemctl enable kindle2notion-web
sudo systemctl status kindle2notion-web
```

✓ 緑色で `active (running)` と表示されれば成功。終了は `q` キー。  
× `failed` の場合 → 第4部「症状別トラブルシュート」の「502 / Flask が起動しない」へ。

### 6.2 VPS 内部から疎通確認

▼ **VPS の中 で実行**
```bash
curl -I http://127.0.0.1:5000
```
✓ `HTTP/1.1 401 UNAUTHORIZED` が出ればOK（Basic 認証が効いている証拠）

### 6.3 手元 Windows から HTTPS 到達確認

▼ **Windows ターミナル (手元PC) で実行**
```powershell
Test-NetConnection my-kindle.duckdns.org -Port 443
```
✓ `TcpTestSucceeded : True`

```powershell
Invoke-WebRequest -Uri "https://my-kindle.duckdns.org/" -UseBasicParsing -SkipHttpErrorCheck
```
✓ ステータスコード `401` が返ればOK（Basic 認証ゲートが正しく動いている）

### 6.4 スマホからアクセス

1. スマホの **Wi-Fi を切って** モバイル回線（4G/5G）にする
2. ブラウザで `https://my-kindle.duckdns.org/` を開く
3. ID / パスワード入力欄に **5.7 で設定した WEB_USERNAME / WEB_PASSWORD** を入れる
4. Web UI が開けば完成 🎉

---

## 7. 第4部: 動かないときの自己診断（トラブルシュート）

### 7.1 症状別ガイド

| 症状 | 主な原因 | 対処 |
|---|---|---|
| ブラウザでタイムアウトする | Oracle のセキュリティリストでポート開放漏れ | 4.4 のセキュリティリスト設定を再確認 |
| `502 Bad Gateway` | Flask（kindle2notion-web）が落ちている | `sudo journalctl -u kindle2notion-web -n 200` でログ確認 |
| `404 Not Found`（Caddy） | Caddyfile のドメイン書き換え漏れ | 5.6 を再実行 |
| HTTPS にならない / 証明書エラー | DuckDNS の IP と VPS の実 IP が不一致 | `dig +short my-kindle.duckdns.org` の結果が VPS の IP と一致するか確認 |
| Basic 認証は通るが画面が真っ白 / 進捗が止まる | Caddy が SSE をバッファリングしている | `/etc/caddy/Caddyfile` に `flush_interval -1` が入っているか確認 |
| Notion 保存で 401 / 404 | 4.2 で **Integration をデータベースに接続していない** | データベース右上「⋯」→「接続を追加」 |
| Playwright がブラウザを開けない | Chromium 未インストール | 下記 7.3 のコマンドで再インストール |
| Amazon ログインで 2 段階認証から先に進まない | 単に時間がかかっているだけ。Web UI のコード入力欄に届いた番号を入れる | — |

### 7.2 確認コマンド集

▼ **VPS の中 で実行**（自分が今どのレイヤーで詰まっているか調べる）
```bash
# アプリ本体
sudo systemctl status kindle2notion-web
sudo journalctl -u kindle2notion-web -n 100 --no-pager

# Web サーバー(Caddy)
sudo systemctl status caddy
sudo journalctl -u caddy -n 100 --no-pager

# DNS 解決（VPS の IP が返ってくるか）
dig +short my-kindle.duckdns.org

# Flask への内部接続
curl -I http://127.0.0.1:5000

# ファイアウォール
sudo ufw status
```

▼ **Windows ターミナル (手元PC) で実行**
```powershell
# VPS への SSH 到達性
Test-NetConnection <VPS_IP> -Port 22

# HTTPS 到達性
Test-NetConnection my-kindle.duckdns.org -Port 443

# 名前解決
nslookup my-kindle.duckdns.org
```

### 7.3 Playwright 再インストール

▼ **VPS の中 で実行**
```bash
sudo -u kindle2notion /opt/kindle2notion/.venv/bin/python -m playwright install chromium
sudo /opt/kindle2notion/.venv/bin/python -m playwright install-deps chromium
sudo systemctl restart kindle2notion-web
```

### 7.4 Windows ターミナル特有のハマり

| エラー / 症状 | 対処 |
|---|---|
| `用語 'ssh' は ... 認識されません` | 設定 → アプリ → オプション機能 → 「**OpenSSH クライアント**」を追加。PowerShell を再起動 |
| `用語 'ssh-copy-id' は ... 認識されません` | Windows には無い。本ガイド 5.2 のワンライナーを使う |
| 秘密鍵で `Permissions are too open` 警告 | 下記コマンドで権限を引き締める |
| 日本語が文字化けする | `chcp 65001` で UTF-8 に切替 |
| 複数行コマンドを貼り付けたら途中で実行されてしまう | **1行ずつ** 貼り付ける。または Windows Terminal の設定で「貼り付け時に複数行警告」を有効化 |
| `Permission denied (publickey)` | 鍵パス指定漏れ。`-i "$HOME\.ssh\kindle2notion_vps"` を必ず付ける |

▼ **Windows ターミナル (手元PC) で実行**: 秘密鍵の権限を引き締める
```powershell
icacls "$HOME\.ssh\kindle2notion_vps" /inheritance:r /grant:r "${env:USERNAME}:R"
```

---

## 8. 付録A: 自宅 Wi-Fi 内だけで動かしたい場合（Windows ローカル実行）

VPS なしで、自宅 PC を起動している間だけ、同じ Wi-Fi 内のスマホからアクセスする構成です。

### 8.1 Python をインストール

1. https://www.python.org/downloads/ から Python 3.11 以上をダウンロード
2. インストーラで **「Add Python to PATH」に必ずチェック** を入れて Install
3. 確認:
   ▼ **Windows ターミナル (手元PC) で実行**
   ```powershell
   python --version
   ```

### 8.2 リポジトリを取得してセットアップ

▼ **Windows ターミナル (手元PC) で実行**
```powershell
# 好きなフォルダに clone（例: C:\Users\<あなた>\Documents）
cd $HOME\Documents
git clone https://github.com/tabear25/kindle2notion.git
cd kindle2notion

# 仮想環境を作って依存をインストール
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements\requirements.txt
playwright install chromium
```

> ⚠ `Activate.ps1` で「このスクリプトは実行できません」と出たら、管理者で PowerShell を開いて  
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`  
> を1回実行してから再度 Activate してください。

### 8.3 KEYS.env を作成

`config\KEYS.env` をメモ帳で新規作成し、第5.7 と同じ内容を書き込みます（`WEB_HOST=127.0.0.1` の行は外しても可）。

### 8.4 起動

▼ **Windows ターミナル (手元PC) で実行**
```powershell
python web_main.py
```

起動すると次のような表示が出ます:
```
Local access:   http://127.0.0.1:5000
Wi-Fi access:   http://192.168.x.x:5000
```

- Windows Defender ファイアウォールのダイアログが出たら **「許可」** を選ぶ
- 同じ Wi-Fi 上のスマホで `http://192.168.x.x:5000` を開けばアクセス可能
- 終了は `Ctrl + C`

---

## 9. 付録B: 今後の運用（GitHub に push → 自動デプロイ）

VPS にデプロイした後は、GitHub Actions を使って **`main` ブランチに push するだけで自動的に VPS が最新版に更新される** ようにできます。

### 9.1 GitHub Secrets を登録

`tabear25/kindle2notion` のリポジトリページで:  
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | 値 |
|---|---|
| `VPS_HOST` | `my-kindle.duckdns.org`（または VPS_IP） |
| `VPS_USER` | `ubuntu` |
| `VPS_SSH_KEY` | `type "$HOME\.ssh\kindle2notion_vps"` で表示される **秘密鍵の全文**（`-----BEGIN ...` から `-----END ...` まで） |
| `VPS_PORT` | `22` |

### 9.2 動作確認

ローカルで何か変更して push すれば、GitHub Actions が自動で VPS に SSH 接続し、`git pull` + サービス再起動を行います。

---

## 10. 用語集

| 用語 | 意味 |
|---|---|
| **Windows ターミナル / PowerShell** | Windows に標準搭載されているコマンド入力アプリ。本ガイドのすべての「手元 PC 側コマンド」はこれで実行 |
| **VPS** | Virtual Private Server。インターネット上に借りる仮想 PC。本ガイドでは Oracle Cloud の Always Free 枠を使用 |
| **SSH** | リモートのサーバーに安全にログインする仕組み |
| **systemd** | Linux でアプリを常駐起動・自動再起動させる仕組み |
| **Caddy** | Web サーバー。Let's Encrypt で HTTPS 証明書を自動取得してくれる |
| **DuckDNS** | 無料でサブドメインを発行してくれるサービス（`〜.duckdns.org`） |
| **Basic 認証** | ブラウザでサイトを開くときに ID/パスワードを要求する素朴な認証方式 |
| **SSE** | Server-Sent Events。サーバーからブラウザへ進捗をリアルタイムで送る仕組み（本アプリの進捗バー表示に使用） |

---

困ったら **第4部** に戻り、「症状別ガイド」と「確認コマンド集」で現在地を特定してください。
