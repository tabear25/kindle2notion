# android/ — APK 版アプリ

デプロイ済みの Web 画面（`frontend/`、Vercel）を WebView で開く薄いネイティブアプリです。
同期・進捗・2FA・手動追加はすべて Web 画面側の処理で、このアプリが足すのは次の 4 つだけです。

- ホーム画面ウィジェット（「Kindle同期」「手動で追加」）
- アイコン長押しのショートカット（同期 / 手動で追加 / 接続先を変更）
- 共有先「ハイライトに追加」
- 起動待ちの間に画面を消さないブリッジ（`window.K2NAndroid.setKeepScreenOn`）

どの入口も、PWA 版と同じ `?action=sync|manual` / `?share_title=&share_text=` 付きの URL を開くだけです（`LaunchUrls.java`）。
使い方は [`docs/ANDROID_APP.md`](../docs/ANDROID_APP.md) を参照してください。

## ビルド

```bash
android/build.sh        # 単体テスト → ビルド → 署名 → android/build/kindle2notion.apk
android/build.sh test   # 単体テストだけ（普通の JVM で動く）
```

Gradle は使いません。このリポジトリを扱うクラウド環境から Google のダウンロード元（dl.google.com / maven.google.com）に届かないためです。
代わりに Ubuntu のパッケージ（dx・zipalign・apksigner・API 23 の android.jar）と、Maven Central の apktool-cli に同梱された aapt2 とフレームワークリソースを使います。
apktool-cli は SHA-256 を固定して検証します。必要なツールはスクリプト冒頭のコメントにあります。

## 署名鍵

公開リポジトリなので、鍵はコミットしません。`K2N_KEYSTORE` / `K2N_KEYSTORE_PASS`（任意で `K2N_KEY_ALIAS`）で渡し、指定がなければ `android/build/` に使い捨ての鍵を作ります。
Android は同じ鍵で署名した APK しか上書き更新できないため、鍵が変わったビルドを入れるには先にアンインストールが必要です。

## 構成

| パス | 役割 |
| --- | --- |
| `AndroidManifest.xml` | minSdk 26 / targetSdk 34、ランチャー・共有の受け口・ウィジェット |
| `src/.../MainActivity.java` | WebView、初回の URL 設定画面、読み込み失敗時の画面、ブリッジ |
| `src/.../LaunchUrls.java` | 入口ごとの URL の組み立て、URL の正規化と同一オリジン判定（Android 非依存） |
| `src/.../SyncWidgetProvider.java` | ウィジェットの 2 ボタン |
| `res/` | 文字列・アダプティブアイコン・ウィジェットのレイアウト・ショートカット定義 |
| `test/.../LaunchUrlsTest.java` | `LaunchUrls` の単体テスト（`build.sh test`） |
