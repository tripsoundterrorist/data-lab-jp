# Production lifecycle-observation migration gate v0.1

`scripts/apply-lifecycle-observation-migration.py` is the explicit runner for
the local production SQLite database. It does not replace the copy-only
migration script.

It requires an exact `--db` path, full pre-migration `--expected-sha256`, and
an existing `--backup-dir`. Without `--apply`, it performs only read-only
preflight and creates neither backup nor database objects.

With `--apply`, it rejects active native collection runs, SQLite WAL/SHM
sidecars, schema incompatibility, changed hashes, an existing target table, or
any backup failure. It creates and validates a backup with the established
backup implementation before one `BEGIN IMMEDIATE` transaction creates the
additive table and index. It preserves canonical logical state of items,
snapshots, and runs; checks integrity and foreign keys; and requires zero
lifecycle observations.

It never restores, automatically retries, starts a collector, contacts an API,
writes D1, deploys, or enables a production route. Output contains only fixed
status/error codes and aggregate counts.
