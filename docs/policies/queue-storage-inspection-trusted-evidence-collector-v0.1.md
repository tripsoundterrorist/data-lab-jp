# Queue Storage Inspection Trusted Evidence Collector v0.1

## Purpose and scope

This read-only collector attests the fixed production Queue and Checkpoint store
configuration without invoking Queue storage inspection. It constructs the
existing production stores, validates the binding and Queue identity, and
checks that both stores have writes disabled and resolve only to the fixed
formal locations.

## Evidence boundary

The collector delegates binding and identity checks to the existing Callable
Binding contract and Core. It requires Queue and Checkpoint write flags to be
false, the existing shared store relationship, and exact fixed path resolution.
No path or Queue identity is emitted. The candidate evidence is revalidated by
the Runtime Preflight Evidence Contract before attestation.

Successful collection returns `PREFLIGHT_EVIDENCE_COLLECTED` and
`evidence_attested=true`. This attests the read-only configuration at collection
time only. It does not establish freshness for a later call, so
`activation_allowed` and `invocation_allowed` remain false. Invalid binding,
identity, writable configuration, schema failure, or internal error fails
closed without evidence.

## Operational protection

The collector may read filesystem metadata needed by existing safe path checks,
but creates or modifies no runtime artifact. It does not invoke
`inspect_production_queue_storage`, read Queue contents, persist state, update
attempts, access an API or DB, dispatch notifications, modify Scheduler or power
settings, or acquire locks. Collector, Backup, and Stale Check capacity remains
prioritized.

## Next gate

Define an atomic preflight-to-invocation coordinator only after a separate
activation approval. Until then, callable execution remains prohibited. The
independent development-efficiency sequence may proceed with GitHub Actions CI.
