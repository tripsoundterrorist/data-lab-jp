# Development Fresh Usage-Protected Start Adapter v0.1

## Purpose

This default-disabled composition places Development Usage Evidence Freshness
v0.1 before the existing Usage-Protected Start Adapter v0.1. A downstream
`START_NEXT_GATE` adapter can be reached only through both guards.

## Ordered guards

1. Production-disabled construction fails before any evaluation or downstream
   call.
2. Stale, future, malformed, or untrusted snapshots fail with no downstream
   call and retain their checkpoint requirement and reason codes.
3. Fresh snapshots are converted and passed to the existing usage permit and
   development-readiness composition without changing their payload.
4. Capacity thresholds, task size, and operational reserve remain owned by the
   existing Usage Protection Permit.
5. A fully permitted path calls the injected downstream adapter at most once.
   Failure, exception, and uncertainty retain existing no-retry behavior.

## Preserved boundaries

The composition reads no clock and supplies no usage collector, polling,
checkpoint, test, commit, push, CI, approval, task-start implementation,
filesystem, network, subprocess, GitHub, Notification, Executor, Production
Queue, billing, or LIVE action. Existing source contracts and Coordinator
semantics are unchanged. There is no production activation factory.
