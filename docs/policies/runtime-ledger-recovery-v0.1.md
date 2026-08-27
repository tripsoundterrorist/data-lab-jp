# Runtime / Ledger Recovery v0.1

## Purpose, scope and non-goals

Read-only diagnostics for the notification ledger, lock and atomic temporary
artifacts. This is not an automatic repair system. No deletion, replacement,
initialization, rename, unlock, process kill, resend, credential access or external
send occurs in Recovery. Queue, approval, Temporal, Publication, DB and scheduler
state remain outside its scope. No direct review-notification path is added.

## Recovery states

| State | Meaning | LIVE |
|---|---|---|
| HEALTHY | Valid path, snapshot/version/schema, no duplicate identities, lock or temp artifacts | Candidate only; existing Runtime/Sender rules still apply |
| RECOVERABLE_NO_WRITE | Snapshot missing, no suspicious artifacts; diagnostic complete without creation | Blocked |
| MANUAL_REVIEW_REQUIRED | Corruption, rejected path, lock or temp artifacts | Blocked |
| RECOVERY_BLOCKED | Read/inspection failure or unknown internal condition | Blocked |

An empty but explicitly initialized valid `[]` snapshot is healthy. A missing
file is not evidence of empty delivery history. Recovery never initializes it.
The existing record validator, version and duplicate-key parser are reused;
both conflicting and identical duplicate identity records are invalid, consistent
with Ledger v0.1. Invalid input never becomes an automatically emptied snapshot.

## Runtime preflight

Runtime inspects the selected store before entering its normal ledger transaction
and before Adapter/Sender/credential access. LIVE requires HEALTHY. DRY_RUN and
MOCK_RUNTIME may proceed from HEALTHY or missing-only RECOVERABLE_NO_WRITE;
manual/blocked states stop delivery in all modes. MOCK remains isolated to temp.
Suppressed/in-memory-duplicate events still return without unnecessary ledger I/O.
Diagnostics may also be run at startup via the inspection entrypoint below.

Preflight is a point-in-time diagnosis, not a filesystem transaction or proof of
future write permission. The existing transaction lock and snapshot validation
remain in force after preflight. A later write failure still returns the existing
safe Ledger result; Recovery never retries or rolls back Queue state.

## Locks and temp artifacts

Ledger v0.1 lock files have no reliable owner/PID information. A present lock is
UNKNOWN, or STALE_CANDIDATE when its modification time is at least one hour old.
Age is only a diagnostic hint, never evidence that an owner is dead. Active
contention cannot be conclusively identified from this format. All present locks
block LIVE; no automatic unlock/lock stealing or process inspection/kill occurs.

Matching atomic temp artifacts are classified VALID_CANDIDATE,
MALFORMED_CANDIDATE, UNKNOWN or MIXED_CANDIDATES. All require manual review.
Candidates are never promoted or deleted. At most 64 matching files are inspected;
excess is UNKNOWN. Reads are bounded by Ledger's existing size limit. Links and
non-regular artifacts are not followed. Unrelated files are not opened.

## Report and inspection

`python -B scripts/ledger_recovery.py --check`

The command reads the default ledger without creating directories, acquiring a
lock, writing files, accessing `.env` or sending anything. Exit 0 means HEALTHY;
exit 2 means further review/blocking. An isolated fixture may be inspected with
`--check --test-ledger <path-under-system-temp>`.

The report contains recovery version/status, sanitized ledger version/path class,
corruption flag, lock status, temp presence/classification, record/duplicate counts,
required action, UTC check time and fixed reason codes. Unknown quantities are
null or UNKNOWN, not guessed. Raw paths, record identities, unknown version text,
credentials, notification text, payloads, responses and exceptions are excluded.

## Security and operator recovery procedure

The existing trusted-local-directory assumption remains. Rejected symlink/junction
paths require review; inaccessible paths block diagnostics. Portable standard
library checks cannot prove Windows ACL ownership or future write access. No
permission/ownership change or privileged repair is attempted.

1. Confirm all LIVE notification runtimes are stopped; a lock's age is insufficient.
2. Inspect ledger, lock and temp artifacts read-only; keep notification delivery blocked.
3. Make a controlled backup copy for human investigation (not automated here).
4. Determine the corruption/interruption/permission cause without changing Queue state.
5. Have an operator decide the remedy and explicitly authorize any repair.
6. Only then perform the separately authorized repair/restore/initialization or stale
   lock handling. Do not blindly promote temp files or discard delivery history.
7. Rerun Recovery check.
8. Require HEALTHY before considering restart.
9. Resume LIVE only under the existing explicit confirmation and notification policy.

Pushover and local Ledger still have a delivery-to-record crash window. Manual
reset or incomplete restoration can allow duplicates; this remains best-effort
persistent deduplication, not a guaranteed at-most-once delivery system.

No LIVE smoke test is part of this change.
