# Durable Remote Approval Coordinator v0.1

This test-scoped coordinator joins the existing iPhone observation adapter and
remote approval replay persistence. Production construction remains disabled.

An approval is released as updated Gate evidence only after `save_record()`
returns `SAVED`. That result is the durable certainty point because Persistence
has already completed revision CAS, atomic replacement, and exact read-back.
The coordinator must not perform a second load, second save, rollback, retry, or
attempt decrement after that result.

Before observing an approval, the coordinator loads replay state once, requires
the caller's exact revision, and blocks consumed request IDs. A stale revision
returns `APPROVAL_CONFLICT`, `durable=false`, with no automatic retry. A replay
returns `APPROVAL_REPLAY_BLOCKED` and cannot release approved evidence.

Pending observation or uncertain persistence returns
`REMOTE_APPROVAL_UNCERTAIN` or `RECOVERY_BLOCKED`, with `durable=false` and no
updated evidence. Denial and invalid targeting also fail closed. Exceptions are
treated as uncertain outcomes.

The coordinator cannot start the next Gate and performs no Executor,
Notification, Queue, Production, LIVE, GitHub, network, or device writes. It
does not change the Core, observation, record, or persistence contracts.
