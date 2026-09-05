# Revenue MVP Unlock Checklist v0.1

`scripts/revenue_mvp_unlock_checklist.py` は既存のDB Handoff PreflightとRevenue MVP
Release Gateを変更せずに集約し、解除作業を優先順で返すread-onlyチェックリストである。
配備、公開、DB更新、公式回答の自動承認は行わない。

優先順は、元DBとSHA-256による同一性・整合性確認、DMM/FANZA core公式回答、
本番shell、Search Console、検証済みPublic Data artifact、Publication Readinessとする。
入力不足、不整合、内部例外はfail-closedとし、パス、SHA-256、URL、例外、credentialを
結果へ含めない。

全条件が揃っても結果は`READY_FOR_FINAL_RELEASE_GATE`までで、
`production_release_allowed`は常にfalseである。本番反映にはRelease Gateの再実行と
別の明示承認が必要となる。
