# Queue Identity Contract v0.1

## Authoritative logical configuration

The user explicitly approved `data-lab-unattended-main` in Queue Notification
Integration Completion Gate v0.1 as the non-secret identifier of DATA LAB's
current main unattended Job Queue. This policy is the source of truth; Core's
MAIN_QUEUE_ID is its explicit code representation, not an inferred default.
No production queue state or credential configuration is created or changed.

The same logical queue retains this exact value across Python/Windows restarts,
Scheduler reruns, cwd/repository relocation, hostname changes and machine
replacement when migrating the same logical queue. This does not assert that
its jobs or execution history persist. Another independent logical queue must
receive a different explicitly approved policy assignment. v0.1 authorizes only
the main queue; arbitrary names are rejected even if syntactically safe. Neither
cloning a repository nor copying this identifier creates a new logical identity.
This policy does not enforce distributed uniqueness or prevent concurrent copies.

## API, schema and validation

`get_queue_identity()` returns a fresh immutable QueueIdentity with four fields:

| Field | Approved value |
|---|---|
| identity_version | 0.1 |
| queue_id | data-lab-unattended-main |
| identity_status | CONFIGURED |
| reason_code | POLICY_BACKED_LOGICAL_IDENTITY |

`validate_queue_identity(identity) -> bool` is the Core-owned validation API.
It checks exact type/schema/string fields, supported version, existing Core
safe ASCII identifier rules, exact approved value and configuration status/reason.
No case folding, trimming, inference or fallback occurs. Empty, malformed,
secret-like, unknown-source, unsupported or unapproved identities return false.
Raw dicts must first be explicitly reconstructed as QueueIdentity. Serialization
and validation are deterministic and read-only. Dispatch must reuse this validator.

## Prohibited sources and unchanged contracts

Never derive identity from hostname, Windows username, PID, clock, UUID, MAC,
repository path/name, Git branch/SHA/remote, Scheduler name, Runtime mode,
notification transport, credential or .env. Core reads none of these for identity.
No environment setting, filesystem access or hashing is needed.

No existing constructor/signature or JobContract, QueueDecision,
QueueBlockedDecision schema changes. No job, approval, retry, checkpoint,
dependency, priority, ordering or scheduling mutation. QUEUE_IDLE and
QUEUE_BLOCKED semantics and existing job-level Dispatch remain unchanged.
QueueIdentity is separate input for a future approved integration, not attached
to a decision or notification in Stage A.

## Origin and persistence limitations

This identifier is public logical configuration, not an authentication token,
OS security principal, cryptographic origin proof, signed provenance or persisted
queue ownership proof. A directly constructed conforming object can validate.
Validation does not prove the caller actually operates the named queue.
No persisted decision/transition history, durable event sourcing, replay
prevention, stale-snapshot detection or cross-process provenance is supplied.

## Future integration gate and non-goals

QUEUE_BLOCKED Dispatch requires a safe event schema that explicitly supports
queue-level identity. Never put queue_id in job_id as a substitute. This contract
alone does not authorize schema extensions, event generation, Runtime identity
changes, Ledger writes, Scheduler changes or LIVE activation. No notification
coupling, transport, automatic recovery, production deployment or state writes.
