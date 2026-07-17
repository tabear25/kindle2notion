# NotebookLM 100ファイル化 — 残作業と論点（2026-07-17 時点）

NotebookLM のソース上限拡張（50 → 100）に合わせ、分割レイアウトを
49ボリューム+索引1（計50ファイル）から **99ボリューム+索引1（計100ファイル）** へ
拡張する作業の進行状況メモ。コード側は完了済み、**実データの再配分がユーザー作業待ち**で
停止している。

- 作業ブランチ: `claude/kindle-highlights-100-split-i49w8n`
- 対象 Drive フォルダ: `notebooklm`（ID: `1iE3aC5Iy5b3w8gxKU2FPNTJHVGu1zurm`）

---

## 1. 完了済み（push 済み）

- `scripts/split_per_book.py`: `VOLUME_COUNT = 99` へ変更。割当式 `SHA1(book_id) % 99 + 1`。
  ファイル名は `k2n_vol_01`〜`k2n_vol_99`（2桁ゼロ埋めのまま）。
- 一回限りの移行コマンド **`--redistribute`** を新設:
  - 全100ファイルが揃うまで**読み書きせず中断**（部分実行で本を落とさない）
  - 全ボリューム読み込み完了後にのみ書き込み（read-all-before-write-any）
  - `--apply` 時は書き込み前にローカル JSON バックアップ（`backups/redistribute-<ts>.json`、
    git-ignore 済み）を出力。中断時は `--redistribute --from-backup <file> --apply` で再開
  - `highlight_id`・重複判定キーは本単位なので移行で変わらない（fake Drive 検証で
    全件一致・移動0件・索引 `last_synced_at` 引き継ぎを確認済み）
- ドキュメント更新: `.claude/CLAUDE.md` / `README.md` / `docs/NOTEBOOKLM_SETUP_TODO.md`
  （Apps Script のループ上限 `i <= 99` に変更済み）/ `docs/MANUAL_HIGHLIGHTS.md` /
  `.claude/skills/adding-manual-highlights/SKILL.md`
- 実データへの dry-run 実施済み: フォルダは生存、既存 50 ファイル検出、
  事前チェックが `k2n_vol_50`〜`k2n_vol_99` の欠落を検出して正常に停止

---

## 2. 残作業（上から順に）

### 2-1. 【ユーザー】新規50ファイル `k2n_vol_50`〜`k2n_vol_99` を作成する

サービスアカウントは Drive にファイルを作れないため、人間の操作が必要。方法はどちらか:

- **a) Apps Script 再実行（推奨）**: <https://script.google.com> の以前のスクリプトを開き、
  ループ上限を `i <= 99` に変えて実行（更新版全文は `docs/NOTEBOOKLM_SETUP_TODO.md` にある）。
  フォルダ ID は `1iE3aC5Iy5b3w8gxKU2FPNTJHVGu1zurm`。既存ファイルはスキップされるので安全。
- **b) Claude が Google Drive コネクタで作成**: セッション上でツール実行を承認すれば代行可能。

### 2-2. 【ユーザー】クラウド環境変数を修正する

- `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` の値が破損している（値の先頭にキー名
  `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=` が重複、JSON 内の `https://` が `https:/` に潰れている）。
  設定画面で **`{` で始まる JSON そのもの**を貼り直す。
  ※ 移行作業自体はセッション側で修復済みの一時ファイルを使うため、これは恒久対応。
- `NOTEBOOKLM_PARENT_FOLDER_ID=1iE3aC5Iy5b3w8gxKU2FPNTJHVGu1zurm` を追加設定する。
  現在は未設定のため旧マスタ経由のフォールバックに落ち、旧マスタ（`GOOGLE_SHEETS_SPREADSHEET_ID`
  の `14NpdB-...`）が 404 になる。ローカルの `config/KEYS.env` にも同様に設定しておく。

### 2-3. 【Claude】dry-run 再実行 → `--apply` → 検証

ファイル作成完了の連絡を受けたらセッション側で実施:

```bash
# 1) dry-run: 100ファイル検出・収穫総数・分布・不変条件を確認
python -m scripts.split_per_book --redistribute --parent-folder 1iE3aC5Iy5b3w8gxKU2FPNTJHVGu1zurm

# 2) 本番書き込み（推定 7〜8 分。直前にバックアップ JSON が出力される）
python -m scripts.split_per_book --redistribute --apply --parent-folder 1iE3aC5Iy5b3w8gxKU2FPNTJHVGu1zurm

# 3) 検証: dry-run をもう一度実行し、総数一致・移動 0 件を確認
python -m scripts.split_per_book --redistribute --parent-folder 1iE3aC5Iy5b3w8gxKU2FPNTJHVGu1zurm
```

中断した場合は再収穫せず `--from-backup <バックアップJSON> --apply` で再開する。

### 2-4. 【ユーザー】NotebookLM で全ソースを再取り込みする

再配分で全ボリュームの中身が変わるため、NotebookLM 側の全100ソースを取り込み直す
（既存49ソースの更新 + 新規51ソースの追加。上限100ちょうどに収まる）。

### 2-5. 【ユーザー】ローカルのテストを更新する

`test/` は git-ignore のためリポジトリに無く、クラウドからは更新できない。
ローカルの `test/test_split_per_book.py` 等で `VOLUME_COUNT = 49` や特定の
ボリューム番号・`vol_NN` ファイル名・49/50 のレイアウトサイズを前提にした
アサーションを 99+1 前提に更新する。新設の純関数 `plan_redistribution` のテスト追加も推奨。

### 2-6. 【ユーザー】ブランチのマージ

移行完了・動作確認後、`claude/kindle-highlights-100-split-i49w8n` を `main` にマージする
（PR 作成は未実施。必要なら依頼してください）。

---

## 3. 残論点（未確定 — 実行前に本人確認が必要なもの）

1. **50ファイルの作成方法**: 上記 2-1 の a / b どちらで進めるか。【未確定】
2. **旧マスタ `kindle2notion_master` の扱い**: `notebooklm` フォルダ内に残っている
  （ファイル名が `k2n_` パターン外なので移行処理には影響しない）。廃止済みデータなので
   別フォルダへ移動または削除してよいか。【未確定・削除は不可逆のため要承認】
3. **`GOOGLE_SHEETS_SPREADSHEET_ID` の今後**: 参照先の旧マスタ ID が 404。
   `NOTEBOOKLM_PARENT_FOLDER_ID` 設定後はフォルダ解決に不要だが、
   `GOOGLE_SHEETS_ENABLED` の判定には依然この変数が必要（コード仕様）。
   404 のままでも動作はするが、生きている ID（例: フォルダ内の `kindle2notion_master`）へ
   差し替えるか、判定仕様を変えるかは未決。【未確定】

---

## 4. 確定事項（再掲）

- 構成は 99ボリューム + 索引1 = 100ファイル（NotebookLM 上限ちょうど）
- 移行は全件再分配方式（NotebookLM 全ソース再取り込みは了承済み）
- 移行の実行はクラウドセッション側で行う（認証情報は環境変数から。ただし 2-2 の破損に注意）
- `VOLUME_COUNT` と割当式は今後も load-bearing: 再変更時は `--redistribute` の再実行と
  NotebookLM 再取り込みが再度必要になる
