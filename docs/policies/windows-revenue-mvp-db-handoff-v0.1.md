# Windows Revenue MVP DB Handoff v0.1

`scripts/prepare-revenue-mvp-db-handoff.ps1`は、ユーザーが明示したWindows上の元DBを
read-onlyで確認し、handoffに必要なSHA-256と集計結果だけをJSON出力する。既定DBパスを
推測せず、symlink/reparse pointを拒否する。

PowerShellの`Get-FileHash`をDB監査の前後で実行し、途中変更を検出する。SQLiteの
integrity、foreign key、商品・snapshot・collection run件数、観測期間は既存の
`revenue_mvp_db_audit.py`へ委譲する。

実行例：

```powershell
powershell -NoProfile -File .\scripts\prepare-revenue-mvp-db-handoff.ps1 -DatabasePath .\data\data-lab.db
```

出力された`expected_sha256`と元DBファイルを対で引き渡す。スクリプトはDBのコピー、
アップロード、削除、更新を行わず、DBパス、Pythonパス、例外内容を結果へ含めない。
