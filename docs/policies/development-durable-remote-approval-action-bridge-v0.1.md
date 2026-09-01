# Durable Remote Approval Action Bridge v0.1

This test-scoped bridge binds one supplied remote approval observation and
expected replay revision to the existing Durable Remote Approval Coordinator.
It exposes the result through the existing `REQUEST_APPROVAL` action contract.

Only the exact `REMOTE_APPROVAL_APPLIED_DURABLY` result with `durable=true`, no
replay flag, and evidence re-evaluating to `NEXT_GATE_READY` becomes a successful
Gate action. Uncertain persistence remains `UNCERTAIN` without evidence. Replay,
revision conflict, denial, recovery block, disabled automation, malformed result,
or exception cannot advance the Gate and is never retried.

The bridge calls the durable coordinator at most once. It does not load or save
replay state itself, so the existing single-load/single-save durability contract
is unchanged. It has no production factory and cannot start the next Gate.

No Queue, Executor, Notification, GitHub, network, device, Production, or LIVE
write is added. Existing Core, observation, codec, persistence, and coordinator
semantics remain unchanged.
