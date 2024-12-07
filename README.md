# これは何（What's this?）
Kindleのハイライトを取得し、NotionのDBに格納するシステムです。

# 前提条件（Prerequisites）
ハイライトを取得する[Kindleメモとハイライト](https://read.amazon.co.jp/notebook)は日本語のサイトです。
Amazonアカウントの言語設定は動作自体には影響しません。

## 必要なライブラリ（Required Libraries）
`requirements.txt`にまとめてあるので全てインストールしてください

# 使い方（How to Use）

### 1. 準備（Preparation）
1. **Notionでデータベース（=DB）を作成する**
   - Notion上でDBを作成してください。
   - DBのフォーマットは以下の通りにしてください
   - 別で何か追加したければ4列目以降に自由に追加できますが、最初の3列は絶対このフォーマットで作成してください。

   | Title  | Content | Page  |
   |-------|------|-------|

2. **Notion API（無料）を取得する**
   - [Notion API](https://www.notion.so/profile/integrations)から自分のNotion APIを作成し、控えてください
   - [参考](https://qiita.com/ulxsth/items/3434471ac91f8fa311cf)：「インテグレーションを作成する」セクションが参考になります

3. **DBID（無料）を取得する**
   - 1で作成したDBのID（=DBID）を取得します。
   - DBのページで共有用URLを取得した以下の部分を控えておきます。
   ```
   https://www.notion.so/<データベースID>?v=<ビューID>
   ```
   - [参考](https://qiita.com/ulxsth/items/3434471ac91f8fa311cf)：「アクセスしたいDBのIDを確認する」セクションが参考になります

4. **自分のAmazonアカウントのIDとPWを確認する**
   - 覚えていない、分からないとは言わせません。

5. **自分のAmazonが2段階認証が有効になっているのかを確認する**
   - 大半の人が有効になっているかと思います。
   - Amazonアカウント内の設定で何かしらのAuthentificatorに通知が飛ぶようにしておくと便利です。
   - 有効になっていない人は `amazon/login.py`の以下の部分を削除してください
   ```
       # 2段階認証の対応
    print('ログインのために2段階認証コードを入力してください。60秒待機します。')
   ```

6. **環境変数ファイルを作成する**
   - 2-5のステップで集めた情報を、環境変数ファイルに以下のフォーマットで記述してください
   ```
   # AmazonアカウントのID
    AMAZON_EMAIL=
    # Amazonアカウントのパスワード
    AMAZON_PASSWORD=
    # NotionAPIキー
    NOTION_API_KEY=
    # NotionDBのキー
    NOTION_DATABASE_ID=
    ```
    
    
### 2. 実行する（Run the Script）
   - 全ての設定が完了したら、`kindle2notion`でスクリプトをrunします。
   ```
   python main.py
   ```
   - 二段階認証画面が表示されたら認証コードを60秒以内に入力してください。
   - 60秒経過後に認証コード入力が成功していると、自動的にハイライトの取得が始まります（なので、60秒ここで待ってください）。

### 注意点（Notes）
- 特にないと思います。
- DBに落としたハイライトは煮るなり焼くなり好きに使うといいと思います。
- 少しでも読書モチベの向上につながると嬉しいです。