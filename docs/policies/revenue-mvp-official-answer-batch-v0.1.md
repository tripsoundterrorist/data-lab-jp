# Revenue MVP Official Answer Batch v0.1

`scripts/revenue_mvp_official_answer_batch.py`は、DMM/FANZA公式回答を事前にsanitizeした
12項目の構造化判断として一括検証するpure intakeである。raw email、本文、送信者、URL、
credential、ファイルパスは受け付けず、Gmail、DB、Issue、Publication Gateを変更しない。

各項目は`ALLOWED`、`CONDITIONALLY_ALLOWED`、`UNKNOWN`、`FOLLOW_UP_REQUIRED`のいずれかとする。
許可系には公式根拠確認が必須で、条件付き許可は条件実装・確認が完了するまでMatrix上で
blockingとなる。不明・要追加確認はfail-closedを維持する。

安全な入力は既存Official Answer Matrixへ委譲する。全12項目が解決しても、出力は
`ACCEPTED_FOR_MANUAL_REVIEW`かつ`gate_unlock_allowed=false`であり、自動で公開条件や
Issue #66を更新しない。反映にはsanitize済み差分の別commitと明示reviewが必要である。
