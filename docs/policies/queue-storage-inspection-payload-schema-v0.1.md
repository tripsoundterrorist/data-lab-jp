# Queue Storage Inspection Payload Schema Candidate v0.1

## Scope

This candidate defines one exact local read-only job profile for future Queue
storage inspection. It validates schema metadata only. It does not admit the
payload through Queue Input v0.1, call `inspect_production_queue_storage()`, read
files, persist state, start an Executor, or authorize production execution.

## Fixed profile

- job_type: `queue_storage_inspection`
- risk_class: `READ_ONLY`
- payload_mode: `LOCAL_READ_ONLY`
- provenance: `BUILTIN_POLICY`
- parameters: none
- preflight: `PRODUCTION_WRITE_DISABLED`, `QUEUE_IDENTITY_VALID`
- runtime budget: 5 seconds
- output allowlist: `HEALTHY`, `LOCKED`, `MANUAL_REVIEW_REQUIRED`,
  `MISSING_REQUIRES_BOOTSTRAP`, `RECOVERY_BLOCKED`

The JobContract must be fresh `READY`, attempt zero, unapproved, require no
approval, and have no dependencies or blockers. Job and payload identity/type
must match exactly. Caller-supplied paths, commands, arguments, provenance,
output fields, timeouts, or parameter codes are rejected.

## Result semantics

An exact candidate returns `PAYLOAD_SCHEMA_VALID` and
`LOCAL_READ_ONLY_SCHEMA_VALID`. `execution_allowed` remains false. Invalid or
extended schemas fail closed without echoing input.

## Operational protection

This candidate does not inspect the production Queue and does not touch the DB,
Collector, Backup, Stale Check, credentials, notifications, Scheduler, power
settings, locks, or temporary artifacts. Existing operational capacity remains
reserved.

## Next gate

A separate Queue Input integration contract may recognize this exact schema.
Even after integration, actual inspection invocation requires an Executor
contract that pins the callable, enforces the runtime budget, validates the safe
output allowlist, and retains `PRODUCTION_WRITE_DISABLED`.
