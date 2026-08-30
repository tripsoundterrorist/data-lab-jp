# Unattended Queue Persistence Contract v0.1

Phase A/B implements a strict, fail-closed Queue document and a temporary-root
storage foundation. It does not bootstrap or write the production Queue, enqueue
jobs, execute transitions, resume work, approve work, retry work, notify, or
access DB, Ledger, Scheduler, credentials, Temporal, or Publication state.

The exact envelope fields are `persistence_version`, `queue_version`, `queue_id`,
`revision`, `jobs`, and `active_checkpoint_refs`. Jobs serialize only the existing
Core `JobContract` fields. References are exact version/job/storage-ID records,
are sorted by job ID, and are unique. Unknown fields, versions, identities,
duplicate JSON keys, noncanonical bytes, invalid Core jobs, and unknown reference
jobs block recovery. The immutable `PersistedQueueSnapshot` remains separate from
Core; Core validators retain all scheduling and state semantics.

Canonical documents are compact, sorted-key, ASCII-escaped UTF-8 without BOM or
trailing newline. Job order is preserved and references are sorted. Queue reads
are bounded at 16 MiB. Revision saves use expected-revision CAS and a single
Queue coordination lock. The save writes and fsyncs a same-directory temporary
file, atomically replaces the Queue file, and validates a read-back. Locks and
temporary residue fail closed; no stale unlock, force mode, repair, revision
reset, or automatic bootstrap exists.

Phase B filesystem entry points require an explicit absolute temporary test root.
Production path activation and bootstrap remain later gates. Missing Queue means
`MISSING_REQUIRES_BOOTSTRAP`. RUNNING, WAITING_APPROVAL, FAILED_SAFE, DONE, and
CHECKPOINTED values round-trip unchanged. CHECKPOINTED without a reference is
Core-valid but inspection requires manual review. Persistence adds no payload,
handler, input, action, retry schedule, raw exception, or active-reference field
to Core.
