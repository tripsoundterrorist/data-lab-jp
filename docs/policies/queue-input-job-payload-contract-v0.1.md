# Queue Input / Job Payload Contract v0.1

## Purpose and scope

This pure contract validates fresh Queue admission metadata and binds exactly one
typed payload contract to every JobContract. It does not persist a Queue, create
or execute commands, read configuration, access credentials, call an API or DB,
dispatch notifications, or change Scheduler definitions.

## Fresh Queue input

The input uses the approved QueueIdentity and delegates JobContract and complete
Queue validation to Core. v0.1 admits 1–256 jobs. Every job must be a fresh
`READY` job with `attempt_count=0` and `approval_received=false`. Dependencies,
risk, approval requirements, blockers, deadlines, retry policy, and all other
JobContract semantics remain Core-owned.

## Payload binding

Every job has exactly one JobPayloadContract. Payloads are sorted and unique by
job_id, and job_id/job_type must exactly match the corresponding JobContract.
Unknown versions, missing, duplicate, orphaned, mismatched, or untyped payload
contracts fail closed.

v0.1 permits only `payload_mode=NO_PAYLOAD` with an empty `parameter_codes`
tuple. It accepts no command, argument, path, URL, credential, API or affiliate
identifier, secret, handler, free text, raw data, or exception. Type-specific
executable payload schemas require separate policy and implementation Gates.

## Result semantics

A valid input returns `QUEUE_INPUT_ACCEPTED`, `admission_allowed=true`, and
`NON_EXECUTABLE_INPUT_VALID`. `execution_allowed` is always false, including for
valid input. Invalid input returns `QUEUE_INPUT_REJECTED` with deterministic
fixed reason codes and no input echo.

## Operational protection

Collector, Backup, and Stale Check are not represented as executable payloads in
v0.1. Their Scheduler definitions, run cadence, credentials, paths, databases,
and operational capacity remain unchanged and take priority over automatic
development.

## Next gate

Define one explicit job-type payload schema at a time, beginning with a local
read-only or DRY_RUN task. Each schema must specify exact parameters, provenance,
preflight, output contract, resource budget, and failure handling before any
Executor or production activation is considered.
