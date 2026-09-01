# Development Chain Usage-Protected Start Integration v0.1

## Scope

This test-only Gate extends the existing observation-chain integration through
the final `NEXT_GATE_READY` boundary. It composes the existing freshness and
usage-protected start adapter with an injected mock start action.

No production start implementation, scheduler, Git/GitHub action, credential,
polling, retry, automatic approval, or automatic merge is added.

## Required behavior

- The checkpoint, test, commit/push, CI, and explicit iPhone approval chain
  must reach `NEXT_GATE_READY` before start evaluation.
- A fresh, trusted usage snapshot that preserves operational reserve may invoke
  the injected start action exactly once.
- A stale snapshot blocks before the downstream action and requires a durable
  checkpoint.
- Unknown five-hour or weekly capacity blocks before the downstream action and
  requires a durable checkpoint.
- Existing stop thresholds (five-hour remaining at 10% or less, weekly
  remaining at 15% or less) block before the downstream action and require a
  durable checkpoint.
- The production adapter remains disabled and has no built-in start path.

## Preserved boundaries

The usage thresholds and operational reserve policy are unchanged. Production
and LIVE remain disabled. This Gate does not bypass explicit approval, infer
capacity, start a real Gate, or alter the existing blocked-task transition to a
separate safe task.
