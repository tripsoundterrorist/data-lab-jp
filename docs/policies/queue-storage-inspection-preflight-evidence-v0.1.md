# Queue Storage Inspection Runtime Preflight Evidence Contract v0.1

## Purpose and scope

This pure candidate contract fixes the shape of future runtime preflight
evidence. It does not collect, attest, persist, or trust evidence and does not
invoke the inspection callable. Caller-supplied true values never establish a
runtime fact.

## Exact candidate

The candidate binds to Callable Binding v0.1, the fixed persistence module and
inspection symbol, `BUILTIN_RUNTIME_PREFLIGHT_CANDIDATE` provenance, the exact
`PRODUCTION_WRITE_DISABLED` and `QUEUE_IDENTITY_VALID` observation codes, and
the five-second budget. Binding and Queue identity are revalidated through the
existing binding contract and Core.

An exact candidate returns `RUNTIME_PREFLIGHT_EVIDENCE_UNATTESTED` and
`TRUSTED_EVIDENCE_COLLECTOR_REQUIRED`. Structural validity does not imply
attestation. `evidence_attested`, `activation_allowed`, and
`invocation_allowed` remain false. Altered, missing, untyped, extended, or
exceptional inputs fail closed without source-value echo.

## Operational protection

There is no evidence collector, attestation API, callable invocation, storage
inspection, path read, Queue write, attempt update, API, database, notification,
Scheduler, power, or lock capability. Existing Core, Persistence, Queue Input,
schema, Result, Executor Decision, Callable Binding, Collector, Backup, and
Stale Check semantics remain unchanged.

## Next gate

Define a trusted, read-only Preflight Evidence Collector with explicit source
provenance and no inspection invocation. It must establish write-disable and
Queue identity facts immediately before any later activation decision. Do not
start until the five-hour usage window has sufficient protected capacity.
