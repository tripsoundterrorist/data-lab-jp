# Development Remote Approval Replay Record v0.1

Status: pure record-contract Gate; no durable writer.

## Purpose

This contract defines the only sanitized record that may later prove one
supplied Codex Remote iPhone approval request has already been consumed. It is
a prerequisite for replay-safe durable approval handling; it does not acquire,
authenticate, persist, or apply an approval.

## Exact record and fail-closed snapshot

- Only an exact `APPROVED` Remote Approval Observation v0.1 together with the
  existing adapter's exact successful validation result can build a record.
- The updated evidence must re-evaluate as `NEXT_GATE_READY`; Gate IDs, pushed
  head SHA, and successful CI run ID must match the observation exactly.
- Source, repository and device class remain fixed to `CODEX_REMOTE`,
  `tripsoundterrorist/data-lab-jp`, and `IPHONE`.
- Request ID, distinct Gate IDs, pushed head SHA, positive CI run ID, and
  non-negative decision epoch are strictly validated.
- The record excludes request time, user identity, notification content,
  credentials, device identifiers, transport data, and arbitrary metadata.
- Extra, missing, malformed, denied, pending, or unknown fields fail closed.
- Duplicate request IDs or duplicate Gate/SHA/CI targets invalidate the entire
  supplied snapshot; no latest-wins or automatic repair is allowed.

Read-only lookup distinguishes `APPROVAL_ALREADY_CONSUMED` from
`APPROVAL_NOT_CONSUMED`. Invalid lookup identity or snapshot blocks evidence.

## Preserved boundaries and next Gate

The codec performs no clock read, filesystem, network, subprocess, GitHub,
Codex Remote, checkpoint, Queue, Executor, Notification, Production, billing,
LIVE, commit, push, merge, retry, rollback, or mutation. It does not change the
existing approval observation or Coordinator result semantics.

A later independently reviewed Gate may add CAS plus atomic replacement and
exact read-back persistence. That writer must persist a successful approval
record before allowing the supplied approval action to advance, and uncertain
persistence must remain fail closed without retry, rollback, second save, or
automatic next-Gate execution.
