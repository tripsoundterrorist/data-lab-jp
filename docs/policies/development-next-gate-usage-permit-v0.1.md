# Development Next Gate Usage Permit v0.1

## Purpose

This pure contract combines Development Gate Evidence v0.1 with Development
Usage Protection Permit v0.1. A next Gate is selectable only when development
evidence is already `NEXT_GATE_READY` and current usage evidence independently
permits the declared task size.

## Ordered decision

1. Development evidence is evaluated first. Rejected or incomplete evidence
   blocks before usage evidence is considered.
2. Unknown, invalid, stop-threshold, large-task-buffer, or operational-reserve
   usage evidence blocks next-Gate selection.
3. The usage contract's checkpoint requirement and reason codes are preserved.
4. Only both successful decisions return `NEXT_GATE_PERMITTED`.

## Preserved boundaries

The contract performs no lookup, polling, checkpoint, test, commit, push, CI,
approval, task start, filesystem, network, subprocess, GitHub, Notification,
Executor, Production Queue, billing, or LIVE action. It does not change either
source contract or authorize the existing Coordinator's production-disabled
adapters. A separately reviewed Gate is required before any coordinator
integration.
