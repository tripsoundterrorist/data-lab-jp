# Revenue MVP Data Candidate Gate v0.1

DB baseline audit、Public Data candidate生成、artifact validation、Publication Gateを1コマンドで接続するread-only Gate。候補はメモリ上だけで生成し、repository、`/data`、Cloudflare、本番環境へ書き込まない。

DB欠落、schema不整合、integrity異常、FK違反、空データではcandidate生成を開始しない。builder・validatorの例外詳細、DB path、商品名、URL、public ID、credentialは結果へ出力せず、`CANDIDATE_BUILD_FAILED`でfail-closedとする。

`LOCAL_CANDIDATE_VALIDATED`はartifactの構造・allowlist・digest・secret/path/URL検査が通ったことだけを示す。production公開許可ではない。現在はLifecycle、Semantics、Publication Status Gateが閉じているため、結果の`publication_allowed`は常にfalseである。

実行例：

```text
python scripts/revenue_mvp_data_candidate_gate.py --db data/data-lab.db
```

公式回答の代替にはせず、公式blocker解消後もproduction build、deployment preflight、別commit、明示承認を必要とする。
