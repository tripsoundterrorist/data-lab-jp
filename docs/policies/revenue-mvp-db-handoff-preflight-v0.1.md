# Revenue MVP DB Handoff Preflight v0.1

実DBはGitHubへcommitせず、認証情報や商品データをログへ出さない。移送元で計算したSHA-256と受領DBを照合し、SQLiteをread-only auditしてからPublication Artifact候補の生成へ進む。

`HANDOFF_READY`には、通常ファイル、symlink不使用、移送元SHA-256との一致、audit前後のSHA-256一致、必須schema、非空データ、integrity check、外部キー検査の合格が必要である。パス、digest、商品識別子、タイトル、URLは結果へ出力しない。不一致・検査中の変更・欠落・判断不能は`BLOCKED`とし、コピー、修復、初期化、収集、公開を実行しない。

実行例：

```text
python scripts/revenue_mvp_db_handoff_preflight.py --db data/data-lab.db --expected-sha256 <移送元で確認した64桁SHA-256>
```

合格後も`revenue_mvp_data_candidate_gate.py`、Artifact Validator、Publication Gate、Deployment Preflight、公式回答レビュー、別の公開承認が必要である。
