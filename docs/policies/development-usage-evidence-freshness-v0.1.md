# Development Usage Evidence Freshness v0.1

## Purpose

This pure contract prevents an old development-usage snapshot from being
treated as current next-Gate evidence. Version 0.1 accepts only explicitly
`USER_CONFIRMED` snapshots and a caller-supplied evaluation timestamp.

## Freshness boundary

- Both timestamps are strict non-negative epoch-second integers.
- Future observations fail closed.
- A snapshot is fresh for at most 300 seconds; the exact boundary is accepted.
- Stale, malformed, unknown-source, or wrong-version snapshots return no usage
  evidence and require checkpoint-safe stopping.
- A fresh snapshot is converted without changing its capacity, task-size, or
  operational-reserve values. Development Usage Protection Permit v0.1 remains
  the sole owner of those semantic decisions.

## Preserved boundaries

The evaluator reads no clock and performs no screenshot extraction, usage
lookup, polling, filesystem, network, subprocess, checkpoint, test, commit,
push, CI, approval, task start, GitHub, Notification, Executor, Production
Queue, billing, or LIVE action. It does not activate or modify the existing
start adapter. Freshness integration requires a separately reviewed Gate.
