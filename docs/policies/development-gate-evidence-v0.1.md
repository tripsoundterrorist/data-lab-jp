# Development Gate Evidence Contract v0.1

## Purpose

This pure contract connects the development sequence `checkpoint → test →
commit/push → CI → next Gate`. It validates evidence and returns exactly one
safe next action. It does not perform that action.

## Ordered decisions

1. A missing checkpoint returns `CHECKPOINT_REQUIRED / SAVE_CHECKPOINT`.
2. A durable checkpoint without tests returns `TEST_REQUIRED / RUN_TESTS`.
3. Passing tests without an exact pushed commit returns
   `COMMIT_PUSH_REQUIRED / COMMIT_AND_PUSH`.
4. An exact pushed commit without CI evidence returns `CI_REQUIRED / WAIT_FOR_CI`.
5. Successful CI at the exact pushed SHA evaluates the approval boundary.
6. `REQUIRED` returns `APPROVAL_REQUIRED / REQUEST_APPROVAL`; only `APPROVED`
   or `NOT_REQUIRED` returns `NEXT_GATE_READY / START_NEXT_GATE`.

`SAVED` and idempotent `NO_CHANGE` are the only accepted durable checkpoint
statuses. Test tier is restricted to FAST, REGRESSION, or FULL. Checkpoint
references are lowercase SHA-256 identities, commit and pushed SHA must be the
same lowercase 40-hex value, and CI must report that exact head with a positive
integer run ID.

## Fail-closed boundary

Malformed, partial-but-contradictory, failed, queued, unknown, mismatched, or
denied evidence returns `EVIDENCE_REJECTED / NONE`. Current and next Gate IDs
must be sanitized and distinct. A rejected result never selects a recovery,
retry, rollback, merge, or alternate Gate.

The evaluator performs no filesystem, network, subprocess, Git, GitHub, Queue,
checkpoint, Executor, notification, production, LIVE, approval, or test write.
Existing Core/Persistence semantics and production checkpoint-write prohibition
remain unchanged.

## Next Gate

A later coordinator may consume the decision and call separately authorized
adapters. It must revalidate evidence after every external boundary and must not
infer CI success, approval, or a pushed SHA from local state.
