# Revenue MVP Isolated Artifact Pipeline v0.1

`scripts/revenue_mvp_isolated_artifact_pipeline.py`は、受領した元DBのSHA-256同一性と
SQLite整合性をread-onlyで確認し、新規の一時ディレクトリだけへPublic Data候補を生成する。
リポジトリ内、既存ディレクトリ、本番出力先は拒否する。

生成前にin-memory artifact検証を行い、DBが生成処理中に変化していないことを再確認してから
一度だけ隔離出力する。出力後もファイルを読み直して検証する。入力DB、Git、Cloudflare、
Issue #66、Publication Gateは変更しない。

検証成功は`LOCAL_ARTIFACT_VALIDATED`であり、`publication_allowed=false`、
`production_write_performed=false`を維持する。公式回答と別の公開承認が揃うまで、生成物を
本番bundleへ含めてはならない。
