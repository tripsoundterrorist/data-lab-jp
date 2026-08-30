# Queue Storage Inspection Result Contract v0.1

## Purpose and scope

This pure contract validates an already-produced aggregate
`ProductionStorageInspectionResult`. It does not invoke storage inspection,
read files, access paths, persist Queue state, or authorize an Executor.

## Output boundary

The result must use Persistence result version 0.1 and exactly one output code
from the payload schema allowlist: `HEALTHY`, `LOCKED`,
`MANUAL_REVIEW_REQUIRED`, `MISSING_REQUIRES_BOOTSTRAP`, or
`RECOVERY_BLOCKED`. Unknown output codes fail closed and are not echoed.

All booleans and nonnegative counts use exact types. State counts must be
sorted, unique, limited to Core job states, and total the declared job count.
Queue, checkpoint, active-reference, unreferenced, and corruption aggregates
must be internally consistent. Persistence metadata is either complete and
version 0.1 or absent. v0.1 retains `confirmed_orphan_count=None`; it does not
invent orphan classification.

Reason codes are bounded, sorted, unique uppercase tokens. Artifact,
checkpoint, and action values use fixed allowlists. HEALTHY, missing, locked,
manual-review, and recovery outputs must match their existing action and
artifact semantics. Contradictory fields fail closed.

## Result semantics

An exact result returns `INSPECTION_RESULT_ACCEPTED`,
`INSPECTION_OUTPUT_ALLOWED`, and the allowlisted output code. Invalid input
returns `INSPECTION_RESULT_REJECTED` with fixed validation reason codes and no
source-value echo. `execution_allowed` is always false.

## Operational protection

This contract has no storage inspection, file, Queue write, Persistence write,
Executor, API, database, notification, Scheduler, lock, path, credential, or
power capability. Existing Core, Persistence, Queue Input, schema, Collector,
Backup, and Stale Check semantics are unchanged.

## Next gate

Define a pure Executor decision contract that composes the admitted Queue Input
and accepted result boundaries, while still prohibiting callable invocation.
Only a later activation Gate may pin `inspect_production_queue_storage()`,
enforce the five-second runtime budget and `PRODUCTION_WRITE_DISABLED`, and
execute the read-only call.
