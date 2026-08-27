# DATA LAB Job Queue Runtime Integration v0.1

The runtime connects exact Unattended Job Queue safe events to Pushover
Notification Adapter v0.1 and Pushover Sender v0.1. It does not reimplement
queue selection, risk or approval policy, message/priority mapping, credential
loading, or URL validation.

`JOB_WAITING_APPROVAL`, `JOB_FAILED_SAFE`, `QUEUE_BLOCKED`, and `JOB_COMPLETED`
are automatically selected. `JOB_STARTED`, `JOB_CHECKPOINTED`, `JOB_SWITCHED`,
and `QUEUE_IDLE` are suppressed before adapter or sender invocation.
`CRITICAL_STOP` is delegated without priority downgrade; Sender v0.1 blocks its
emergency delivery.

Modes are `DRY_RUN` (default), `MOCK_RUNTIME`, and `LIVE_NOTIFICATION`. Live
notification requires explicit confirmation. Notification failure never rolls
back or mutates queue/job state and never changes retry, Gate, database, or
production state.

Optional in-memory duplicate detection stores only a SHA-256 identity derived
deterministically from the exact safe event. Session duplicates return
`DUPLICATE_EVENT_SUPPRESSED`. Persistent Notification Ledger v0.1 additionally
records successful delivery and suppresses restart duplicates with
`NOTIFICATION_DUPLICATE_SUPPRESSED`, before adapter, sender or network activity.
See [the ledger policy](persistent-notification-ledger-v0.1.md) for storage,
mode isolation, corruption recovery and the delivery-to-record crash window.

The exact safe output contains runtime version/mode/status, event type, bounded
selection/delivery booleans, approval/emergency booleans, and safe reason codes.
It excludes credentials, URLs, notification text, raw events/results,
exceptions, tracebacks, and paths.
