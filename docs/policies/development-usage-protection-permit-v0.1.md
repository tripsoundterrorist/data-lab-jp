# Development Usage Protection Permit v0.1

Status: pure decision Gate; no automatic execution.

## Threshold contract

- Unknown 5-hour or weekly remaining capacity fails closed and requires a
  checkpoint before stopping.
- At 10% or less in the 5-hour window, new work stops and checkpoint/test/
  commit-push/next-Gate recording is required.
- At 15% or less weekly, normal automatic development stops with the same
  checkpoint requirement.
- Large tasks are blocked at 15% or less in the 5-hour window and at 20% or
  less weekly.
- Small tasks may continue only above both stop thresholds.
- Collector, Backup, Stale Check and other operational reserve must already be
  protected; otherwise the permit fails closed.

## Preserved boundaries

- The stricter applicable limit wins and all simultaneous stop reasons are
  retained.
- The evaluator performs no usage lookup, polling, scheduling, write, task
  start, commit, push, notification or billing action.
- It does not alter LIVE, approval, Executor or Production Queue behavior.
