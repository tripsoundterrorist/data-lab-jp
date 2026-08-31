# Development Gate Coordinator v0.1

## Scope

The Coordinator consumes Development Gate Evidence v0.1 and invokes at most
one injected adapter for the exact action selected by Core. It then revalidates
the returned evidence before reporting progress.

Production construction is disabled by default. Enabled construction is
test-scoped and there is no production activation factory, built-in Git/GitHub
adapter, credential access, or command execution.

## Single-action progression

- `SAVE_CHECKPOINT` must advance only to `TEST_REQUIRED`.
- `RUN_TESTS` must advance only to `COMMIT_PUSH_REQUIRED`.
- `COMMIT_AND_PUSH` must advance only to `CI_REQUIRED`.
- `WAIT_FOR_CI` may advance only to `APPROVAL_REQUIRED` or `NEXT_GATE_READY`.
- `REQUEST_APPROVAL` must advance only to `NEXT_GATE_READY`.
- `START_NEXT_GATE` requires evidence already classified `NEXT_GATE_READY`.

Skipping stages, returning the wrong action, malformed results, adapter
exceptions, reported failures, and invalid post-action evidence fail closed.
Failed or uncertain actions are never retried, rolled back, compensated, or
followed by another adapter call. Uncertain status remains uncertain.

## Preserved boundaries

The Coordinator does not alter checkpoint, Queue, Core, Persistence, test,
commit, push, CI, approval, Executor, Notification, production, or LIVE
semantics. It performs no built-in filesystem, network, subprocess, GitHub, or
credential operation. Existing operational priority and usage-protection rules
remain external hard prerequisites.

## Next Gate

After this contract passes, separately reviewed adapters may be introduced one
at a time. Read-only CI observation is the safest first adapter. Write-capable
checkpoint, Git, GitHub, approval, and next-Gate adapters remain disabled until
their own authorization and recovery contracts exist.
