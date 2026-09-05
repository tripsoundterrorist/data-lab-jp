# DATA LAB Publication Gate v0.3

Publication GateはPublic Data artifactの権利、データ構造、公式確認、公開状態をfail-closedで評価する。

Lifecycle GateとSemantics Gateはデフォルトで`PENDING_OFFICIAL_CONFIRMATION`を維持する。Issue #66の全core論点がsanitized matrixで解決済みとなり、かつ別途の公式回答レビュー承認が厳密なboolean `true`として明示された場合だけ、両Gateを`PASS`候補へ移行できる。

未回答、不正なdecision、未検証の条件付き許可、承認なし、boolean以外の承認値はいずれもGateを開かない。公式回答だけでは公開できず、rights、data policy、artifact、production build、deployment preflight、`publication_status=public`、別commitの公開承認も必要である。

現在のmatrixは全項目`UNKNOWN`で承認も未設定のため、従来どおりLifecycle/SemanticsはPENDING、公開はBLOCKEDである。
