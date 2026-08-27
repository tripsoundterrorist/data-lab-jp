# Persistent Notification Ledger v0.1

## Purpose and scope

Notification-only **best-effort persistent deduplication** across process
restarts. Queue selection, approval, risk, retry, Temporal, Publication, Gate,
priority, message generation and credential handling remain outside this layer.
Queue, Adapter and Sender source files are unchanged.

## Storage and schema

The default local store is `runtime/notification-ledger-v0.1.json`: a UTF-8 JSON
array with a required final newline. This is not the production database. Each
record has exactly `ledger_version` (`0.1`), `event_identity`, `event_type`,
`delivery_status` (`NOTIFICATION_DELIVERED`), and `recorded_at_utc` (UTC with Z).
Identity is passed directly from Runtime's existing `event_identity` function;
the ledger does not compute a different identity. No event text or credentials
are stored. Store, lock and temporary files are ignored by Git.

## Semantics and atomicity

Absent identity means `NEW`; a stored successful identity returns
`NOTIFICATION_DUPLICATE_SUPPRESSED` before Adapter/Sender/credential access.
Only Runtime `NOTIFICATION_DELIVERED` with `delivery_succeeded=true` is recorded.
Failure, exception, rejection, suppression and emergency block are not successes.
The existing optional in-memory set retains its session semantics; it is distinct
from the persistent success-only store. For restart simulation use a fresh set.

An exclusive sidecar lock spans lookup, send and atomic replacement, so cooperating
processes cannot concurrently deliver the same identity. Contention fails closed
without waiting or retry. Updates write a same-directory temporary file, flush,
fsync, then replace the snapshot. File size is bounded to 4 MiB; capacity exhaustion
fails closed rather than pruning identities. Interrupted temporary files are not
treated as committed records. Filesystem power-loss durability is not guaranteed.

## Crash window and failures

Pushover delivery and local storage share no transaction. A crash after API
success but before replacement can leave a delivered notification unrecorded.
An uncertain timeout can likewise hide a successful remote delivery. A later
attempt can therefore deliver again: this is not an at-most-once guarantee.
Write failure after successful delivery returns `NOTIFICATION_FAILED_SAFE` with
`delivery_attempted=true`, `delivery_succeeded=true` and a safe ledger reason.
This preserves the external success fact without claiming it was persisted.
No automatic retry, Queue rollback or Queue/job-state mutation occurs.

## Corruption and recovery

Invalid JSON, missing final newline, unknown version, extra/missing fields,
invalid timestamp/identity/status, duplicate JSON keys/identities, oversized file
or read failure stops notification delivery. Never silently reset or ignore a
damaged store. A stale lock also blocks delivery and is never stolen automatically.

Recovery is operator-controlled: stop all notification runtimes; preserve the
damaged snapshot and temporary files for investigation; restore a verified valid
backup, validate it in DRY_RUN, then restart. Remove a stale sidecar lock only
after confirming no writer is active. If no valid backup exists, keep delivery
blocked until the operator explicitly accepts potential duplicates from a reset.
This implementation performs no automatic recovery/deletion of existing data.

## Modes and security

- DRY_RUN reads the ledger only: no directory, lock, timestamp or record writes.
- MOCK_RUNTIME defaults to a disposable temp store. Pass `NotificationLedger(path)`
  below the system temp directory to test persistence across calls/processes.
  Production paths are rejected in this mode.
- LIVE_NOTIFICATION defaults to the production store and records successful
  delivery only. Explicit test stores in this mode require injected transport and
  credential loader; tests must never use real credentials or real transport.

Suppressed events return before ledger I/O. CRITICAL_STOP retains priority 2 and
Sender emergency blocking. No emergency fallback is introduced. The existing
Runtime output schema is unchanged. Errors expose fixed codes only. The ledger
does not open `.env`, change permissions, or access DB/state/scheduler systems.
Runtime directories must be trusted local directories; symlink/junction paths are
rejected, but this is not a defense against a hostile user changing paths during I/O.

No LIVE smoke test is performed for this implementation.
