# Development Observation Chain Integration v0.1

## Scope

This test-only Gate verifies the existing read-only observation chain:

1. durable checkpoint result,
2. test-tier result bound to that checkpoint,
3. commit/push result bound to checkpoint and test tier,
4. CI result bound to checkpoint, test tier, pushed SHA, and refs,
5. explicit Codex Remote iPhone approval bound to the same Gate and CI run.

No production coordinator, adapter, workflow, permission, or external action is
added. The integration uses only test-scoped coordinator construction and
supplied immutable observations.

## Required behavior

- Each successful observation advances exactly one stage.
- A mismatched checkpoint, ref, SHA, Gate ID, or CI run fails closed.
- Successful CI with an approval requirement stops at `APPROVAL_REQUIRED`.
- Valid approval advances only to `NEXT_GATE_READY`; it does not start a Gate.
- Usage freshness and usage-permit guards remain mandatory for any separately
  injected `START_NEXT_GATE` adapter.

## Preserved boundaries

There is no filesystem write, Git/GitHub operation, polling, retry, automatic
approval, automatic merge, notification, Production/LIVE behavior, or
next-Gate execution in this integration Gate.
