# Snapshot-title provenance migration v0.1

New collector snapshots store one bounded title in `item_snapshot_titles`,
keyed by the exact snapshot ID. The collector verifies that the supplied
observation timestamp equals `item_snapshots.observed_at`; title, lifecycle
observation, and snapshot are committed by the same collector transaction.
No URL, content ID, affiliate value, raw response, or credential is stored.

Existing snapshots are not backfilled. Their title provenance therefore
remains unknown and cannot satisfy the unordered reduced-surface review
contract.

`migrate-add-snapshot-titles.py` is copy-only. Production migration requires
`apply-snapshot-title-migration.py`, an exact database path and SHA-256, an
existing backup directory, and explicit `--apply`. It rejects active native
runs, SQLite sidecars, schema or hash mismatches, an existing target table, or
backup failure. It creates and validates a backup before one additive
transaction, preserves existing logical state, requires zero automatic
backfill, and verifies integrity and foreign keys.

The runner never restores automatically, starts a collector, calls an API,
writes D1, deploys, changes a publication Gate, or activates a route or CTA.
If a post-backup migration check fails, the transaction is rolled back and the
verified backup is retained for an explicit operator decision.
