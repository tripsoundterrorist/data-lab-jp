# Development Gate CI Observation Adapter v0.2

## Scope

This version preserves the pure, read-only behavior of v0.1 while binding an
already supplied GitHub Actions result to the exact preceding development
evidence. It performs no request, polling, retry, filesystem access,
subprocess, Git operation, GitHub write, or merge.

## Required identity and evidence binding

- Repository is exactly `tripsoundterrorist/data-lab-jp`.
- Workflow is exactly `CI`; source is exactly `GITHUB_ACTIONS`.
- Base branch is exactly `main`.
- Pull-request runs require an allowlisted `codex/` feature branch.
- Push runs require branch `main`.
- Checkpoint reference and preceding test tier exactly match Gate evidence.
- Supplied pushed SHA exactly matches Gate evidence.
- CI head SHA exactly matches both commit SHA and pushed SHA.
- Run ID is a positive integer.

The exact completed job set remains `fast` and `validation`. Both jobs and the
workflow must succeed. FAST evidence is required for `fast`; REGRESSION is
required for pull-request validation and FULL for main-push validation.

Valid queued or in-progress results without a conclusion remain `UNCERTAIN`
without evidence. Unknown status values and incomplete results carrying a
conclusion are contradictory and fail closed. Any identity, binding, ref, SHA,
job, tier, or conclusion mismatch also fails closed without evidence.

## Preserved boundaries

The caller still explicitly supplies whether approval is required. No LIVE or
production behavior, credential, schedule, notification, automatic approval,
automatic merge, commit, push, retry, rollback, or next-Gate execution is
introduced.
