# Development Usage-Protected Start Adapter v0.1

## Purpose

This default-disabled adapter guard connects Development Next Gate Usage Permit
v0.1 to the existing Coordinator's injected `START_NEXT_GATE` boundary. It
provides no built-in task-start implementation.

## Guard order

1. Production-disabled construction always fails without a downstream call.
2. Enabled test construction evaluates development readiness and supplied
   usage evidence before calling the injected downstream adapter.
3. A blocked decision never calls downstream. Its source reason codes are
   retained, and checkpoint-required decisions add
   `USAGE_CHECKPOINT_REQUIRED`.
4. A permitted decision invokes downstream at most once.
5. Exceptions and malformed results fail closed. `FAILED` and `UNCERTAIN`
   downstream results are preserved without retry, rollback, or compensation.

## Preserved boundaries

There is no production activation factory, usage lookup, polling, checkpoint,
test, commit, push, CI, approval, task-start implementation, filesystem,
network, subprocess, GitHub, Notification, Executor, Production Queue,
billing, or LIVE action. Existing Core, Persistence, Coordinator, approval,
blocked-checkpoint, and operational-priority semantics are unchanged.
