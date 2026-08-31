# Development Gate CI Observation Adapter v0.1

## Scope

This pure read-only adapter validates an already supplied GitHub Actions
observation and converts it into `WAIT_FOR_CI` action evidence. It performs no
GitHub request, polling, retry, filesystem access, subprocess, or write.

Accepted identity is fixed to repository `tripsoundterrorist/data-lab-jp`,
workflow `CI`, source `GITHUB_ACTIONS`, and event `pull_request` or `push`. The
observation head must exactly equal the pushed commit SHA and the run ID must be
a positive integer.

## Required CI evidence

- The workflow and both jobs must be completed successfully.
- The exact job set is `fast` and `validation`.
- `fast` must report FAST.
- Pull requests must report REGRESSION for `validation`.
- Main pushes must report FULL for `validation`.

An incomplete run returns `UNCERTAIN` without updated evidence. Failure,
identity mismatch, SHA mismatch, invalid job/tier evidence, and malformed input
return `FAILED`. The adapter does not retry or infer later success.

The caller must explicitly provide whether the next Gate requires approval.
Successful observation then produces either `APPROVAL_REQUIRED` or
`NEXT_GATE_READY` after Coordinator revalidation.

## Preserved boundaries

No GitHub write permission, secret, credential, schedule, notification,
checkpoint, Queue, Executor, production, LIVE, merge, commit, push, or
next-Gate action is introduced. The Coordinator remains production-disabled and
all write-capable adapters remain prohibited.
