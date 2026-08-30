# Queue Input / Storage Inspection Integration Contract v0.1

## Purpose and scope

This pure integration contract permits Queue Input to recognize the exact
`queue_storage_inspection` payload schema v0.1 without authorizing execution.
It composes the existing Queue Input and schema validators. It does not change
Core, Persistence, the existing validators, or production Queue state.

## Recognition boundary

A payload is routed to the schema validator when its job type is
`queue_storage_inspection` or its payload mode is `LOCAL_READ_ONLY`. Both the
JobContract and JobPayloadContract must satisfy the exact built-in schema. This
prevents another job type from acquiring the local read-only mode and prevents
the inspection job type from falling back to `NO_PAYLOAD`.

After exact schema validation, the integration constructs an in-memory
`NO_PAYLOAD` admission view and delegates all Queue identity, freshness, order,
uniqueness, one-to-one binding, and Core Queue checks to the existing Queue
Input validator. The original input is frozen and is not modified.

## Result semantics

Accepted input retains `QUEUE_INPUT_ACCEPTED`, `admission_allowed=true`, and
`NON_EXECUTABLE_INPUT_VALID`. When at least one exact schema is recognized, the
result also includes `QUEUE_STORAGE_INSPECTION_SCHEMA_RECOGNIZED` and the exact
recognized count. `execution_allowed` is always false.

Invalid schema candidates fail closed with
`QUEUE_STORAGE_INSPECTION_SCHEMA_INVALID` plus fixed schema reason codes.
Existing Queue Input failures retain their existing fixed reason codes. No
input values are echoed.

## Operational protection

This contract has no file, Queue storage, persistence, Executor, API, database,
notification, Scheduler, lock, or power capability. It does not call
`inspect_production_queue_storage()`. Collector, Backup, and Stale Check remain
untouched and retain priority over automatic development.

## Next gate

Define a pure result contract for the fixed inspection output-code allowlist.
Actual invocation remains forbidden until a later Executor contract pins the
callable, enforces the five-second budget and `PRODUCTION_WRITE_DISABLED`, and
fails closed on every unrecognized result.
