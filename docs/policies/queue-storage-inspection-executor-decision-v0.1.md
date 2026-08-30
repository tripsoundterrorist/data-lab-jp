# Queue Storage Inspection Executor Decision Contract v0.1

## Purpose and scope

This pure decision contract composes the Queue Input integration and inspection
Result Contract without activating an Executor. It accepts raw boundary values
and delegates validation to both existing validators; callers cannot substitute
fabricated validation-result wrappers.

## Exact decision boundary

Queue Input must admit exactly one job and recognize exactly one
`queue_storage_inspection` schema. Mixed or ordinary Queue inputs are excluded
from this Executor decision. The supplied aggregate inspection result must pass
the Result Contract and contain one of the five fixed output codes.

Passing both boundaries does not establish callable provenance or prove that an
inspection was performed. It returns `EXECUTOR_ACTIVATION_BLOCKED`,
`boundaries_valid=true`, the fixed five-second budget, and
`SEPARATE_ACTIVATION_GATE_REQUIRED`. `invocation_allowed`,
`production_write_allowed`, and `attempt_update_allowed` remain false.

Invalid Queue Input, nonexclusive target jobs, invalid results, validator
exceptions, and unknown output codes return `EXECUTOR_DECISION_REJECTED` with
fixed reason codes and no source-value echo.

## Operational protection

This contract does not bind or call a function, inspect storage, read a path,
persist Queue state, change attempts, start an Executor, access an API or DB,
dispatch notifications, modify Scheduler or power settings, or acquire locks.
Core, Persistence, Queue Input, schema, result, Collector, Backup, and Stale
Check semantics remain unchanged.

## Next gate

Define a pure Callable Binding / Preflight Contract that pins only
`inspect_production_queue_storage`, the five-second budget,
`PRODUCTION_WRITE_DISABLED`, and the approved Queue identity without invoking
the callable. Production activation remains a separate later approval Gate.
