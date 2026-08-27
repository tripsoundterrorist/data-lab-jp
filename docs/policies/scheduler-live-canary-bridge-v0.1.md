# Scheduler LIVE Canary Bridge v0.1

## Scope and gates

Dedicated future Scheduler entrypoint: `scripts/scheduled_runtime_live_canary.py`.
Only the exact argument `--confirm-live-canary-v0.1` authorizes its one canary
cycle. No arguments or any extra/unknown argument blocks with exit 2. This is an
explicit LIVE-capable entrypoint, not a dry-run command. Do not invoke confirmed
CLI during implementation tests. The original Runner CLI remains LIVE-disabled.
No environment variable selects LIVE. This is intended for Scheduler use, but
does not authenticate its parent process: a local operator can invoke it too.

## Fixed event and identity

The nine fields are event_version=0.1, event_type=JOB_WAITING_APPROVAL,
job_id=scheduler-live-canary-v0.1, job_type=notification_canary, severity=WARN,
state=WAITING_APPROVAL, approval_required=true,
summary_code=SCHEDULER_LIVE_CANARY_V01, occurred_at=2026-08-27T00:00:00Z.
The timestamp is a synthetic identity anchor, not the actual send time. A fresh
dictionary is returned each time. This never creates a Queue job or approval.
Runtime validates it and uses its existing SHA-256 event_identity implementation;
the bridge neither computes nor hardcodes a digest. Repeated executions have the
same identity across processes. Do not rotate these fields to defeat deduplication.

## Delegation, recovery and storage

Bridge resolves the source-based repository root, then calls Runner.run_once with
LIVE_NOTIFICATION and explicit confirmation. Runner's HEALTHY Recovery gate,
locking, Runtime, Adapter and Sender remain mandatory. Missing/corrupt/busy/temp
states block without repair. Adapter owns the fixed message, priority 1 and
IMMEDIATE delivery class. CRITICAL_STOP cannot be selected here; the existing
emergency block remains unchanged.

Only Runtime records successful delivery in the default production Ledger.
Same-identity subsequent cycles stop before Sender with
NOTIFICATION_DUPLICATE_SUPPRESSED. No reset, pruning, bootstrap, or ledger write
exists in the bridge. Existing best-effort delivery crash-window limitations apply.

## Output and security

Output contains bridge_version, bridge_status, canary_type, runner_mode,
recovery_status, runtime_invoked, notification_attempted, runtime_status,
duplicate_suppressed, exit_code, reason_codes. Runner mode denotes requested mode,
not proof of invocation. Only allowlisted statuses and fixed reason codes appear;
exceptions and invalid results are not echoed. Uncertain post-dispatch failures
use null invocation/attempt flags rather than claiming no send.
Exit codes: 0 completed or duplicate, 2 safety block, 3 operational failure.
There is no raw event, credential, response, message, path or identity output.
No arbitrary event/priority/payload/identity/path/sender/recovery override is exposed.
Tests patch the internal Runner dependency with isolated fixtures; the production
entrypoint provides no dependency-injection CLI or alternate storage controls.

## Activation procedure and non-goals

Implementation/tests do not register tasks or perform real sends. Later activation
requires separate operator approval and pre/post data, Ledger and task snapshots.
Keep all four existing tasks unchanged. Create a separate initially Disabled task,
same-or-lower principal, AC restrictions and IgnoreNew, with no periodic trigger.
Inspect executable, working directory and exact confirmation arguments before
enabling one canary cycle. Require HEALTHY immediately before activation. Inspect
safe result and ledger count; allow one identical duplicate check only with approval.
Return the task to Disabled afterward. Never delete successful records on failure.
No periodic LIVE service, job executor, Queue mutation, DB/Temporal/Publication
change, credential change, retry, emergency send, deployment or permission change.
