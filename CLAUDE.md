# CLAUDE.md

このリポジトリで Claude Code が作業するときに守ってほしいことを書いています。
利用者向けの一般ドキュメントは `README.md` を参照してください。

## プロジェクト概要

Kindle Notebook (`https://read.amazon.co.jp/notebook`) のハイライトを Playwright
でスクレイプし、Notion DB に保存するツール。任意で Google Sheets にも同時保存できる。
エントリーポイントは 2 つ:

- `python main.py` — ローカル Tkinter GUI (`gui_utils/gui.py:ProgressWindow`)
- `python web_main.py` — Flask + ブラウザ UI (`web/app.py`, `web/pipeline.py`)

両方とも内部では `main.run()` を呼び出し、`amazon/login.py:perform_login` →
`book_transformer/transformer.py:extract_notes` → `notion/toNotion.py` →
(任意) `google_sheets/toSheets.py` のパイプラインを実行する。

## 重要な不変条件

### 1. Tkinter はメインスレッドのみ

`main.py` では Playwright のスクレイプ処理を `_worker` デーモンスレッドに逃がし、
`ProgressWindow` (`tk.Tk` ルート) はメインスレッドで `mainloop()` する。

- ワーカースレッドから **絶対に** 新しい `tk.Tk()` を作らない / `mainloop()` を呼ばない
  (サイレント失敗 / ハング)
- ワーカーから UI を触るときは必ず `self._root.after(0, ...)` でメインスレッドに
  ディスパッチする (例: `ProgressWindow.update`、`prompt_two_factor_code`)
- 第二ウィンドウは `tk.Toplevel(self._root)` を使うこと
- ワーカーから結果を待つ場合は `threading.Event` + 共有 dict で受け取る
  (`gui_utils/gui.py:ProgressWindow.prompt_two_factor_code` と
  `web/pipeline.py:PipelineState.request_two_factor` が同じパターン)

### 2. 2 段階認証 (2FA) のフロー

`amazon/login.py:perform_login` は最大 `MAX_2FA_ATTEMPTS` (=5) 回ループする。

- `two_factor_callback` が `None` かつ `allow_manual_auth=True` のときだけ
  「ブラウザで手入力する」フォールバックに短絡する。それ以外はコールバック経由で
  GUI/Web ダイアログを開く
- コールバックのシグネチャは `(error_message: Optional[str] = None) -> Optional[str]`
  で統一。Amazon が誤コードを返したときは `last_error=TWO_FACTOR_REJECTED_MESSAGE` を
  渡して再ダイアログを出す
- コードを送信したあと `wait_for_selector(TWO_FACTOR_INPUT_SELECTOR, state="hidden")`
  で受理判定する
- ユーザーがキャンセル / タイムアウトしたら `SystemExit` を投げる。`main.py:_worker`
  は `BaseException` で捕捉して `window.mark_error()` で進行ウィンドウを赤に切り替える
  (`except Exception` だと `SystemExit` を取り逃すので注意)

### 3. `_show_input_dialog` と `_build_input_dialog_widgets` の役割分担

`gui_utils/gui.py` で:

- `_build_input_dialog_widgets(window, ..., on_submit, on_cancel)` — 純粋なウィジェット
  ビルダー。`tk.Tk()` を作らない、`mainloop()` を呼ばない、コールバックで結果を返す。
  既存ルート / `Toplevel` のどちらでも使える
- `_show_input_dialog(...)` — 独自 `tk.Tk()` を作るスタンドアロン版。`ask_book_limit`
  のように `ProgressWindow` 生成前に呼ぶケース用

新しいダイアログを追加する場合、`ProgressWindow` 起動中に出すなら
`_build_input_dialog_widgets` + `Toplevel` を使うこと。

## 開発ルール

### ブランチ / コミット

- 開発ブランチは指示された `claude/...` 系ブランチで作業する
- コミットは作業単位で 1 件、push まで行う (PR 作成は明示要求があるときだけ)
- コミットメッセージは英語、命令形、1 行目は短く、本文に「なぜ」を書く

### コードスタイル

- UI 文言は日本語 (Tkinter / Web の両方)
- ログ / コメント / コミットメッセージは英語
- 既存のスタイル定数 (`gui_utils/gui.py` の `WINDOW_BG` 等) を再利用する
- 設定読み込みは `config/__init__.py` 経由 (`load_env_file` / `BASE_DIR`)

### 検証コマンド

```bash
python -m compileall -q .                       # 構文チェック
python -m pytest test -q -p no:cacheprovider    # 自動テスト (test/ がある場合)
playwright install chromium                     # Playwright Chromium セットアップ
```

実機 2FA の確認手順は次のとおり (Tkinter 環境が必要):

1. `python main.py` を起動
2. 冊数入力ダイアログが出ることを確認
3. 2FA 要求アカウントで Chromium に 2FA 画面が出る → Tkinter ダイアログが
   `ProgressWindow` の上にポップアップ
4. コードを入力 → Chromium 側 `#auth-mfa-otpcode` に自動入力されサインイン完了
5. 誤コード時は同じダイアログが「コードが誤っていました...」付きで再表示
6. 「中止」 / × / 5 分タイムアウトで進行ウィンドウが赤エラーに

## 触るときに注意するファイル

- `amazon/login.py` — 2FA ループ + `state="hidden"` 受理判定。ループを 1 回に戻さない
- `gui_utils/gui.py` — `ProgressWindow.prompt_two_factor_code` のスレッドブリッジ。
  `event.wait()` / `root.after(0, ...)` のペアを崩さない
- `main.py:_worker` — `except BaseException` を `except Exception` に戻さない
  (`SystemExit` を取りこぼす)
- `web/pipeline.py:PipelineState.request_two_factor` — `error_message=None` kwarg を
  維持する (`amazon/login.py` がキーワードで渡している)

## CLAUDE.md 自体の更新ポリシー

- アーキテクチャ的に「次回ここを触る人がハマりそうな不変条件」を発見したら追記する
- 一時的な作業ログ / 変更履歴は書かない (それは git log の役目)
