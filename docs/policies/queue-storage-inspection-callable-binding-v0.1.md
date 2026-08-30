# Queue Storage Inspection Callable Binding / Preflight Contract v0.1

## Purpose and scope

This pure contract pins the Queue storage inspection callable symbol and its
required preflight metadata without invoking it. The exact built-in target is
`unattended_queue_persistence.inspect_production_queue_storage`, with zero
arguments and `ProductionStorageInspectionResult` as the declared result type.
No caller-supplied module, callable, path, argument, or provenance is accepted.

## Fixed binding

The binding is version 0.1, job type `queue_storage_inspection`, provenance
`BUILTIN_POLICY`, five-second runtime budget, and the existing five-code output
allowlist. It requires Executor Decision v0.1 status
`EXECUTOR_ACTIVATION_BLOCKED`. Required preflights remain exactly
`PRODUCTION_WRITE_DISABLED` and `QUEUE_IDENTITY_VALID`.

The contract verifies the target symbol identity without calling it and
delegates Queue identity validation to Core. A valid static binding returns
`CALLABLE_BOUND_PREFLIGHT_PENDING`. Identity preflight may be valid, but
production-write preflight remains false and runtime preflight remains required.
The contract does not accept an untrusted boolean as proof that writes are
disabled.

## Result semantics

Valid binding metadata and Queue identity return
`CALLABLE_BOUND_PREFLIGHT_PENDING`, `binding_valid=true`,
`identity_preflight_valid=true`, `production_write_preflight_valid=false`, and
fixed pending reason codes. Invocation and production writes remain false.
Unknown, extended, missing, or mismatched bindings and identities fail closed
without echoing source values.

## Operational protection

This contract does not invoke the callable, inspect storage, read a path,
persist Queue state, update attempts, access an API or DB, dispatch a
notification, modify Scheduler or power settings, or acquire locks. Core,
Persistence, Queue Input, schema, Result, Executor Decision, Collector, Backup,
and Stale Check semantics remain unchanged.

## Next gate

Define a Runtime Preflight Evidence Contract that can prove
`PRODUCTION_WRITE_DISABLED` immediately before invocation while retaining a
closed activation Gate. Production execution remains separately approved.
