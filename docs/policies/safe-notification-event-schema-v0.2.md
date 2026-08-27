# Safe Notification Event Schema v0.2

## Purpose and compatibility

Add explicit JOB/QUEUE subject contracts without changing v0.1 wire meaning,
notification policy, transport or stored Ledger records. No QUEUE_BLOCKED
Dispatch is implemented here. Existing job Dispatch and Scheduler canary continue
to emit v0.1. EVENT_VERSION remains 0.1; EVENT_SCHEMA_VERSION is 0.2.

## Exact schemas

v0.1 retains exactly event_version, event_type, job_id, job_type, severity, state,
approval_required, summary_code, occurred_at. Its existing validation and legacy
event taxonomy remain supported, including its historical queue-named events.
Do not use that legacy shape for new queue-level Dispatch.

v0.2 common fields (8): event_version, event_type, subject_type, occurred_at,
severity, state, approval_required, summary_code.

* JOB adds job_id and job_type (exactly 10 fields).
* QUEUE adds queue_id (exactly 9 fields).

Missing, extra, mixed-subject or unsupported-version fields fail closed. No
nullable job placeholders, aliasing, implicit upgrades, normalization or fallback.
The approved queue_id cannot be substituted for job_id in v0.2.

JOB supports JOB_STARTED, JOB_WAITING_APPROVAL, JOB_FAILED_SAFE, JOB_COMPLETED,
JOB_CHECKPOINTED and JOB_SWITCHED with their existing state/approval semantics.
It requires Core-safe job identifiers and summary code, recognized severity and
timezone-aware occurred_at. CRITICAL_STOP and QUEUE_IDLE are not newly assigned
a v0.2 subject; their v0.1 semantics remain unchanged.

QUEUE supports only QUEUE_BLOCKED. queue_id is validated through the existing
Core QueueIdentity contract; currently only data-lab-unattended-main is approved.
state is the queue-domain decision_status QUEUE_BLOCKED, never a job state such
as BLOCKED, FAILED_SAFE or WAITING_APPROVAL. summary_code is fixed QUEUE_BLOCKED.
approval_required is false according to the existing notification contract:
only JOB_WAITING_APPROVAL uses true. It describes notification approval semantics,
not whether any job inside the queue awaits approval. No queue/job state mutation
or approval decision is implied. Severity uses existing SEVERITIES; time must be
aware, as in the existing event contract. Future Dispatch must copy Core's UTC
decision time unchanged, not synthesize a new time.

## Core ownership

create_event returns immutable NotificationEvent (v0.1), JobNotificationEventV02
or QueueNotificationEventV02 after validation. event_fields_v02 selects shape
only. Core owns subject/event/state/approval consistency and queue identity
validation. Runtime and Adapter delegate v0.2 validation to create_event, rather
than maintaining a second queue_id or blocker validator. Event schema validity
does not establish blocked-decision provenance. Future Dispatch still must call
validate_queue_blocked_decision and validate_queue_identity.

## Runtime identity and compatibility

Runtime retains its one SHA-256 implementation and sorted compact JSON encoding.
For v0.1, exactly the same nine fields/values are hashed with the same encoding:
no subject field, version rewrite or migration is injected. The existing canary
identity remains d3ef3e57785d35ade98cff12e6566695b939c1938b73b6b340d726c934b34fa4
and matches the existing production record. A read-only DRY_RUN confirms its
persistent duplicate suppression without sending.

For v0.2, hash the exact subject-specific field set, including event_version,
subject_type and its real identity. No fake job identity or second hash function.
Different queue_id values affect canonical identity, but a different unapproved
queue_id is rejected for processing. event_identity is a shape-based hashing
helper, not an authorization/validity check; Runtime validates before delivery.
v0.2 JOB identities differ from v0.1 because their explicit version/subject differ.
Existing producers are NOT upgraded: do not replay a legacy event as v0.2 to
bypass its stored identity. No cross-version identity migration is implemented.

## Adapter, Sender and Ledger

Adapter reuses the same fixed message mapping and rendering checks. QUEUE_BLOCKED
remains priority 1 / IMMEDIATE and does not expose queue_id in the message.
Adapter output and Runtime result schemas/versions remain unchanged. Sender and
Ledger storage code are unchanged. Existing Ledger stores opaque event_identity,
event type and delivery metadata, not safe events, queue snapshots, payloads or
responses. Mock duplicate processing stops before Sender using existing Ledger
logic. CRITICAL_STOP emergency sending remains blocked.

## Safety and limits

Only DRY_RUN and fixture MOCK_RUNTIME are exercised; no production LIVE send,
Scheduler change, production Ledger write, credential/config change or migration.
DRY_RUN may check credential presence under existing Sender behavior; tests use
fixture loaders and never load real secrets. Production canary duplicate checking
returns before Sender. All mock writes use temporary Ledger files.

Contracts are not origin authentication, persisted source/decision proof,
stale-snapshot detection or replay prevention. Ledger remains best-effort
notification deduplication with its existing crash window. No Dispatch, Stage C
integration, Stage D readiness, automatic recovery, new event taxonomy, deployment,
commit or push is part of this schema change.
