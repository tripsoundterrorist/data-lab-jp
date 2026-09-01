# Development Remote Approval Replay Persistence v0.1

Status: test-scoped durable persistence Gate; production writes disabled.

## Contract

The store persists only valid Remote Approval Replay Record v0.1 values in one
canonical versioned snapshot. Test bootstrap is explicit. Save uses an
exclusive lock, expected-revision CAS, exclusive temporary creation, file
flush and fsync, atomic replacement, and exact read-back before returning
`SAVED`.

An exact already-consumed request returns `ALREADY_CONSUMED` without a write.
A stale revision returns `STALE_REVISION`. Conflicting request IDs or approval
targets, malformed data, unsafe paths, uncertain read-back, and unexpected
artifacts fail closed. There is no automatic retry, rollback, second save,
revision decrement, latest-wins selection, forced unlock, or temp promotion.

## Preserved boundaries and next Gate

Only an explicit temporary `for_test` store can write. The formal repository
root cannot be a test write root; the shared read-only constructor rejects
bootstrap and save. No production activation factory exists.

This Gate does not acquire or authenticate a Remote approval, advance the
Development Coordinator, merge, start a Gate, send a notification, mutate the
Queue, invoke an Executor, access credentials, activate LIVE, or add billing.
A later coordinator Gate may combine the existing approval observation with
this persistence. It must treat `SAVED` as the durable certainty point without
a second load, block `ALREADY_CONSUMED`, and preserve uncertain persistence
without retry, rollback, or approval application.
