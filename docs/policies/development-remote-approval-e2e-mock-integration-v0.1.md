# Remote Approval End-to-End Mock Integration v0.1

Status: test-scoped end-to-end Gate; Production and LIVE remain disabled.

This integration composes the existing iPhone approval observation, durable
replay coordinator, Action Bridge, and Development Gate Coordinator using a
test-scoped replay store. It proves that one fresh approved observation can be
persisted durably and advance only from `APPROVAL_REQUIRED` to
`NEXT_GATE_READY`.

The flow invokes the approval action once and never starts the next Gate. The
durable coordinator remains the sole replay-store reader/writer: successful
coordination performs one load and one save, and Persistence's `SAVED` remains
the certainty point. The integration adds no read-back, retry, rollback, second
save, attempt decrement, or recovery action.

Replay, stale revision, denial, invalid Gate evidence, malformed state, and
disabled automation fail closed. Pending approval, persistence uncertainty, and
exceptions remain uncertain without releasing next-Gate readiness.

There is no production factory, LIVE mode, external approval acquisition,
notification, Queue, Executor, Scheduler, GitHub, API, device, database, or
public-site write. Existing component semantics are unchanged.
