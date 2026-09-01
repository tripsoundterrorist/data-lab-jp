# Development Automation Activation Preflight v0.1

## Scope

This pure read-only contract validates supplied safety evidence before any
future development-automation activation review. It does not inspect the
environment, construct a production Coordinator, activate an adapter, write,
poll, retry, contact GitHub, or incur cost.

## Required evidence

- Exact repository `tripsoundterrorist/data-lab-jp` and base branch `main`.
- Exact ordered action chain from checkpoint through next-Gate start.
- Observation-chain integration verified.
- Fresh usage guard mandatory.
- Blocked work requires durable checkpoint and a separate safe task switch.
- Collector, backup, and stale-check operational reserve remains protected.
- Every PR merge remains explicitly approved.
- LIVE and production writes remain disabled.
- No additional cost is required.

Missing or malformed evidence fails closed. LIVE or production-write enablement
is blocked. Any additional cost produces `COST_CONFIRMATION_REQUIRED` before
work continues.

## Non-activation boundary

Even complete evidence returns only `PREFLIGHT_READY_FOR_MANUAL_REVIEW`.
`activation_allowed` is always false, manual activation review is always
required, and no production activation implementation is introduced by this
Gate.
