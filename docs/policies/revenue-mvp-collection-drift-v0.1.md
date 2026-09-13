# Revenue MVP Collection Drift v0.1

The read-only drift check compares the mutable Revenue SQLite database with the
validated publication receipt and sanitized D1 row-count evidence. It reports
whether a collection changed only artifact inputs or also added items requiring
a separately approved D1 lookup sync.

`SYNC_REQUIRED_FAIL_CLOSED` is an expected safe state after collection. It does
not authorize artifact publication, D1 export/write, affiliate eligibility,
Gate unlock, deployment, route activation, or paid-plan changes. Count decrease,
D1 evidence ahead of the source database, malformed/permissive evidence,
database corruption, or foreign-key failure returns `FAIL_CLOSED`.

```powershell
python scripts/revenue_mvp_collection_drift.py
```
