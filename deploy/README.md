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

非エンジニアの方でも迷わず、上から順番に実行していけば必ず最後までたどり着けるように、専門用語の解説やPCの操作方法（黒い画面＝ターミナルの使い方など）を補足しながら、超詳細なマニュアルとしてまとめ直しました。

少し長いですが、一つひとつの作業はコピペで終わるものも多いです。焦らず一つずつ進めていきましょう！

---

# 📚 Kindle2Notion 完全セットアップガイド（初心者向け）

このガイドは、あなたの読書ノート（Kindle）をNotionに自動でまとめるシステムを、インターネット上のサーバーに設置（デプロイ）するための手順書です。

**💡 作業を始める前の心構えと準備**
* **「ターミナル（黒い画面）」を使います。**
    * Windowsなら「コマンドプロンプト」または「PowerShell」、Macなら「ターミナル」というアプリを使います。
    * 記載されているコマンド（灰色の四角で囲まれた文字）は、**1行ずつコピーして、ターミナルに貼り付けてEnterキーを押す**だけでOKです。
* **メモ帳を開いておきましょう。**
    * 途中で発行されるパスワードや「IPアドレス」などを一時的にメモしておくために使います。

## 🛠️ 準備：まず最初に決めること

作業中に何度も使う情報を、あらかじめメモ帳（サクラエディタ、メモ帳、Notion等）に書き出しておきましょう。

1.  **DuckDNSのドメイン名**: （例：`my-kindle-note`）
2.  **DuckDNSのトークン**: （例：`abc12345-xxxx...`）
3.  **サーバーのIPアドレス**: （あとで取得します）
4.  **Webログイン用ID**: `admin`（推奨）
5.  **Webログイン用パスワード**: （英数字12文字以上を自分で作成）

---

## 🛠️ 第1部：サーバーと住所の準備

システムを24時間動かし続けるための「土地（サーバー）」と「住所（ドメイン）」を用意します。

### ステップ 1. クラウドサーバー（VPS）を借りる
あなたのパソコンの代わりに24時間動いてくれる、インターネット上のパソコン（VPSといいます）を無料で借ります。

1.  **[Oracle Cloud](https://www.oracle.com/cloud/free/)（推奨）** にアクセスし、無料アカウントを作成します。
    * *※クレジットカードの登録が必要ですが、Always Free（ずっと無料）の枠内であれば課金されません。*
2.  アカウントができたら、管理画面から「インスタンスの作成（パソコンを立ち上げる操作）」を行います。
3.  設定項目は以下の通りにしてください。
    * **OS（中身のシステム）:** `Ubuntu 24.04 LTS` を必ず選んでください。
    * **形（シェイプ）:** `Ampere A1`（推奨：最大4コア/24GBメモリ）を選びます。
4.  作成が完了すると、**「パブリック IP アドレス」**（例：`123.45.67.89` のような数字の羅列）が表示されます。**これをメモ帳にコピーしておいてください。**

### ステップ 2. Web上の住所（ドメイン）を取得する
数字のIPアドレスではアクセスしづらいため、わかりやすい名前（ドメイン）を無料で取得します。

1.  [DuckDNS](https://www.duckdns.org/) にアクセスします。
2.  画面上部の GitHub / Google / Twitter などのアイコンをクリックしてログインします。
3.  「sub domain」と書かれた入力欄に、好きな英数字を入力し、「add domain」を押します。
    * 例：`kindle-taro` と入力すると、あなたの住所は `kindle-taro.duckdns.org` になります。**これをメモします。**
4.  画面上部に **`token`** （例：`a1b2c3d4-xxxx-...`）という長い文字列が表示されています。**これも非常に重要なのでメモします。**

---

## 🔑 第2部：サーバーに入るための「鍵」を作る

サーバーに安全に接続するため、パスワードではなく「自分だけの電子キー（SSH鍵）」を作ります。
**ここから、お手元のパソコンの「ターミナル（黒い画面）」を使います。**

### ステップ 3. 鍵を作成し、サーバーに渡す

1.  手元のパソコンのターミナルを開き、以下のコマンドをコピーして貼り付け、Enterを押します。
    ```bash
    ssh-keygen -t ed25519 -f ~/.ssh/kindle2notion_vps -C "kindle2notion-deploy"
    ```
    *※途中で「パスフレーズ（鍵の暗証番号）を入力してください」と英語で聞かれますが、何も入力せずにそのままEnterを2回押してOKです。*

2.  次に、作った鍵の「片割れ（南京錠）」を、ステップ1で借りたサーバーに登録します。以下のコマンドの `<USER>` と `<VPS_IP>` を書き換えて実行します。
    * `<USER>` は、Oracle Cloudなら `ubuntu` です。
    * `<VPS_IP>` は、ステップ1でメモした数字です。
    ```bash
    # 例: ssh-copy-id -i ~/.ssh/kindle2notion_vps.pub ubuntu@123.45.67.89
    ssh-copy-id -i ~/.ssh/kindle2notion_vps.pub <USER>@<VPS_IP>
    ```

3.  鍵を使ってサーバーにログインします。
    ```bash
    # 例: ssh -i ~/.ssh/kindle2notion_vps ubuntu@123.45.67.89
    ssh -i ~/.ssh/kindle2notion_vps <USER>@<VPS_IP>
    ```
    *※ターミナルの左側の文字が `ubuntu@instance-xxxx:~$` のように変わったら、サーバーの中に入れた証拠です！以降はサーバー内での作業になります。*

4.  **セキュリティ設定（パスワードログインの禁止）**
    以下のコマンドを実行して、設定ファイルを開きます（`nano` というテキストエディタが開きます）。
    ```bash
    sudo nano /etc/ssh/sshd_config
    ```
    キーボードの矢印キー（↓）で下の方へスクロールし、以下の2行を探して書き換えます（もし `#` が先頭にあったら `#` を消してください）。
    * `PasswordAuthentication yes` → `PasswordAuthentication no` に変更
    * `PermitRootLogin yes` （または他の文字） → `PermitRootLogin no` に変更
    変更後、**`Ctrlキー` + `O（オー）`** を押し、**`Enter`** を押し、**`Ctrlキー` + `X`** を押して画面を閉じます。

---

## ⚙️ 第3部：サーバーへのシステムインストール

### ステップ 4. プログラムのダウンロードと初期設定

1.  以下のコマンドを1行ずつ実行し、プログラムをサーバーにダウンロード（clone）して、自動セットアップを開始します。
    ```bash
    sudo git clone https://github.com/tabear25/kindle2notion.git /opt/kindle2notion
    sudo bash /opt/kindle2notion/deploy/setup.sh
    ```
    *※文字がたくさん流れますが、終わるまで数分待ちます。*

2.  次に、ステップ2で取得したDuckDNSの情報をサーバーに教えます。以下の `<YOUR_DUCKDNS_TOKEN>` と `kindle-taro`（ドメインの最初の部分）を**自分のものに書き換えてから**実行してください。
    ```bash
    echo "<YOUR_DUCKDNS_TOKEN>"   | sudo tee /etc/duckdns/token   >/dev/null
    echo "kindle-taro" | sudo tee /etc/duckdns/domain >/dev/null
    sudo chmod 600 /etc/duckdns/token /etc/duckdns/domain
    ```

3.  通信を安全にするための設定ファイル（Caddyfile）を書き換えます。以下の `kindle2notion-yourname` の部分を、**自分のドメイン（例：`kindle-taro`）に書き換えて**実行します。
    ```bash
    sudo sed -i 's/kindle2notion-xxx.duckdns.org/kindle-taro.duckdns.org/' /etc/caddy/Caddyfile
    ```

4.  設定を反映させます。1行ずつ実行します。
    ```bash
    sudo /usr/local/bin/duckdns-update
    sudo systemctl restart caddy
    ```

### ステップ 5. 秘密のパスワードファイル（KEYS.env）の作成

システムがAmazonやNotionにログインするための情報をまとめたファイルを作ります。

1.  ファイルを作成して開きます。
    ```bash
    sudo nano /opt/kindle2notion/config/KEYS.env
    ```
2.  以下の内容をコピーして、開いた画面に貼り付けます。そして、`< >` で囲まれた部分を自分の情報に書き換えます。（書き換え方はステップ6も参照）

    ```env
    AMAZON_EMAIL=<あなたのAmazonのメールアドレス>
    AMAZON_PASSWORD=<あなたのAmazonのパスワード>

    NOTION_API_KEY=<Notionのシークレットキー>
    NOTION_DATABASE_ID=<NotionのデータベースID>

    # あなたのシステムにアクセスするための好きなIDとパスワードを決めてください
    WEB_USERNAME=admin
    WEB_PASSWORD=ここに長くて複雑なパスワードを自分で作って入力
    ```
    *書き換え終わったら、先ほどと同じく `Ctrl + O` → `Enter` → `Ctrl + X` で保存して閉じます。*

3.  このファイルを他の人に見られないように鍵をかけます。
    ```bash
    sudo chown kindle2notion:kindle2notion /opt/kindle2notion/config/KEYS.env
    sudo chmod 600 /opt/kindle2notion/config/KEYS.env
    ```

### ステップ 6. 各種APIキーの取得方法の補足（ステップ5で入力するもの）

* **Notion API Key (`NOTION_API_KEY`)**
    1. [Notion My Integrations](https://www.notion.so/my-integrations) にアクセスし、「新しいインテグレーション」を作成。
    2. 発行された「シークレット」という文字列をコピー。
* **Notion Database ID (`NOTION_DATABASE_ID`)**
    1. 保存先のNotionデータベース（表）をブラウザで開く。
    2. URLの `https://www.notion.so/〇〇〇?v=...` の `〇〇〇` の部分（32桁の英数字）をコピー。
    3. **【重要】** そのデータベースの右上の「･･･」メニューから「コネクトの追加」を選び、先ほど作ったインテグレーションを選択して許可してください。

---

## 🚀 第4部：自動更新の準備と起動確認

### ステップ 7. GitHubにサーバーの鍵を預ける（自動デプロイ用）

今後プログラムがアップデートされた時、自動でサーバーも更新されるように設定します。

1.  **手元のパソコンの別のターミナル画面**（サーバーに接続していない元の画面）を開き、以下のコマンドで先ほど作った「鍵の本体」の中身を表示します。
    ```bash
    cat ~/.ssh/kindle2notion_vps
    ```
2.  `-----BEGIN OPENSSH PRIVATE KEY-----` から `-----END OPENSSH PRIVATE KEY-----` まで、**1文字も漏らさずに全てコピー**します。
3.  ブラウザで、自分のGitHubにある `kindle2notion` のリポジトリ（コピーしたページ）を開きます。
4.  **Settings** ＞ 左メニューの **Secrets and variables** ＞ **Actions** をクリックします。
5.  「New repository secret」という緑のボタンを押し、以下の4つを1つずつ登録します。

| Name (Secret名) | Secret (値) |
| :--- | :--- |
| `VPS_HOST` | ステップ1でメモしたサーバーの **IPアドレス** （またはDuckDNSドメイン） |
| `VPS_USER` | サーバーのユーザー名（Oracleなら `ubuntu`） |
| `VPS_SSH_KEY` | 先ほどコピーした **鍵の中身全部** |
| `VPS_PORT` | `22` と入力 |

### ステップ 8. いざ、初回動作確認！

サーバー側のターミナル画面に戻り、システムを起動します。

1.  起動コマンドを実行
    ```bash
    sudo systemctl start kindle2notion-web
    sudo systemctl status kindle2notion-web
    ```
    *※緑色で `active (running)` と表示されていれば成功です！終了するには `Q` キーを押します。*

2.  **スマホからのアクセス確認**
    正しくインターネットに公開されているか確認するため、スマホのWi-Fiを切り、**モバイル回線（4G/5G）** にします。
    ブラウザ（SafariやChrome）で、ステップ2で作ったあなたの住所にアクセスします。
    👉 `https://自分のドメイン.duckdns.org/`

3.  「ユーザー名」と「パスワード」を求められるので、**ステップ5の `WEB_USERNAME` と `WEB_PASSWORD` で設定した値**を入力します。

4.  画面が開いたら、指示に従ってパイプライン（処理）を1回走らせてみましょう。Amazonの2段階認証コードの入力画面などが出れば、**すべて完璧に設定できています！お疲れ様でした！**

---

## 🔄 今後の運用について（自動デプロイ）

あなたが今後このシステムを保守する際、わざわざサーバーに入り直す必要はほとんどありません。
GitHub上の `main` ブランチに新しいコードを取り込む（PushやSyncする）だけで、裏側でGitHubが自動的にサーバーへ接続し、最新版へのアップデートとシステムの再起動を行ってくれます。

---

## 🚑 困ったときのトラブルシューティング

もしうまくいかない場合は、以下のコマンドをサーバーのターミナルで実行して原因を探ります。

**Q. サイトにアクセスできない（Caddyのエラーかも？）**
* ドメインとIPアドレスが正しく紐付いているか確認します。（IPアドレスが表示されればOK）
    ```bash
    dig +short 自分のドメイン.duckdns.org
    ```
* 通信の通り道（ポート）が開いているか確認します。
    ```bash
    sudo ufw status
    ```
* Webサーバー（Caddy）の内部エラーログを確認します。（終了は `Q` キー）
    ```bash
    sudo journalctl -u caddy -n 200
    ```

**Q. 画面の進捗バーが途中で止まって動かない**
* `/etc/caddy/Caddyfile` の中に `flush_interval -1` という記述が正しく入っているか確認してください。

**Q. ブラウザ操作ツール（Playwright）が起動しないエラーが出る**
* サーバー内で以下の2行を実行して、ツールを強制的にインストールし直してください。
    ```bash
    sudo -u kindle2notion /opt/kindle2notion/.venv/bin/python -m playwright install chromium
    sudo /opt/kindle2notion/.venv/bin/python -m playwright install-deps chromium
    ```

**Q. とにかくシステム全体のエラー内容を見たい**
* 以下のコマンドで、システムのリアルタイムなログを見ることができます。（終了するには `Ctrl + C` を押します）
    ```bash
    sudo journalctl -u kindle2notion-web -f
    ```