# Development Remote iPhone Approval Observation v0.1

## Purpose

This pure adapter validates a supplied Codex Remote iPhone approval observation
for the existing `REQUEST_APPROVAL` Coordinator boundary. It establishes the
contract required before an actual Remote/app integration is considered.

## Exact binding

- Source is exactly `CODEX_REMOTE`, device class is `IPHONE`, and repository is
  fixed to `tripsoundterrorist/data-lab-jp`.
- Request ID, current Gate, next Gate, pushed head SHA, and successful CI run ID
  must identify the approval-required evidence exactly.
- Pending observations remain `UNCERTAIN`; denied, malformed, mismatched,
  future, or older-than-five-minute decisions fail closed with no updated
  evidence.
- Only a fresh exact `APPROVED` observation changes approval status to
  `APPROVED`; the Coordinator then revalidates `NEXT_GATE_READY`.

## Preserved boundaries

This is contract-level validation, not proof of device authentication or an
implemented Codex Remote connector. It performs no device query, app request,
polling, retry, merge, commit, push, checkpoint, CI, task start, filesystem,
network, subprocess, GitHub, Notification, Executor, Production Queue,
billing, or LIVE action. Replay persistence and real-device acquisition require
separately reviewed Gates. Existing approval and Coordinator semantics remain
unchanged.
