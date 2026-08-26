# DATA LAB Unattended Job Queue Core v0.1

This pure local policy selects sanitized job contracts and emits bounded decisions, checkpoints, and notification events. It does not execute jobs, persist runtime state, contact APIs, send notifications, change Task Scheduler or Windows settings, write the database, run Temporal Probe, alter production, deploy, or change any Gate or Official Blocker.

## Selection and risk boundary

The queue selects only `READY` jobs whose dependencies are `DONE`, blocker list is empty, attempts remain, deadline/window facts allow execution, and risk/approval policy allows unattended work. Ordering is P0 through P3, then creation timestamp, then job ID. `READ_ONLY` and `LOW_RISK_LOCAL` are eligible. `EXTERNAL_READ` requires an explicit caller policy flag. `APPROVAL_REQUIRED` requires an explicit approval event. `PROHIBITED_UNATTENDED` never runs.

Unknown versions, states, risks, retry policies, malformed dependencies, duplicate IDs, dependency cycles, contradictory flags, unsafe checkpoints, and internal errors fail closed. Priority never overrides risk. A paused, blocked, approval-waiting, retry-waiting, checkpointed, or safely failed job may switch only to a separately eligible job; otherwise the queue becomes idle.

## Checkpoint, resume, and retry

Checkpoints contain only job ID, state, last completed step, resume preconditions, blocker codes, attempt count, timestamp, and reason codes. URLs, credentials, identifiers, titles, raw responses/exceptions, secrets, and sensitive paths are rejected. Resume revalidates the checkpoint age, dependencies, blockers, approval, risk, and an explicit environment preflight result.

Only temporary network failure, transient file lock, and explicitly retryable local error are retry candidates within the configured attempt limit. Authentication, permission, policy, official-evidence, Gate, secret, and destructive-operation failures become `FAILED_SAFE`.

## Safe events

Notification events use version `0.1` and the exact fields `event_version`, `event_type`, `job_id`, `job_type`, `severity`, `state`, `approval_required`, `summary_code`, and `occurred_at`. They contain no delivery address, URL, credential, raw exception, title, content/product ID, or filesystem path. Event creation does not deliver a notification.
