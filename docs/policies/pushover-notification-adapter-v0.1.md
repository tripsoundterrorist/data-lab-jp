# DATA LAB Pushover Notification Adapter v0.1

## Scope

This pure adapter converts an Unattended Job Queue safe notification event into
a bounded Pushover-safe message contract. Version 0.1 performs no API request,
secret or `.env` read, delivery suppression, persistence, scheduler change, or
production change.

## Input and fail-closed policy

Only the queue's exact nine-field event schema and event version `0.1` are
accepted. Unknown versions, event types, severities or states; extra/missing
fields; malformed timestamps; unsafe identifiers; approval contradictions; and
critical events without `CRITICAL` severity produce `INVALID_INPUT`. Internal
exceptions are reduced to a fixed safe reason code.

URLs, credentials, tokens, raw exceptions, tracebacks, titles, product/content
IDs, and absolute paths are forbidden. Input values are never interpolated into
the title or message. Titles and messages are fixed per event type and are
limited by internal policy to 100 and 512 characters respectively.

## Mapping

| Event | Priority | Delivery class | Emergency candidate |
|---|---:|---|---|
| `JOB_STARTED` | -1 | `SUPPRESSIBLE` | false |
| `JOB_COMPLETED` | 0 | `NORMAL` | false |
| `JOB_FAILED_SAFE` | 1 | `IMMEDIATE` | false |
| `JOB_WAITING_APPROVAL` | 1 | `IMMEDIATE` | false |
| `JOB_CHECKPOINTED` | 0 | `SUPPRESSIBLE` | false |
| `JOB_SWITCHED` | 0 | `SUPPRESSIBLE` | false |
| `QUEUE_IDLE` | -1 | `SUPPRESSIBLE` | false |
| `QUEUE_BLOCKED` | 1 | `IMMEDIATE` | false |
| `CRITICAL_STOP` | 2 | `IMMEDIATE` | true |

`JOB_WAITING_APPROVAL` requires `approval_required=true`; all other events
require false. Priority 2 is only marked as an emergency candidate. Retry,
expire, receipt handling, and actual delivery belong to a future sending layer.

## Output

The exact output allowlist is: `adapter_version`, `notification_status`,
`pushover_priority`, `emergency_candidate`, `delivery_class`, `title`, `message`,
`approval_required`, and `reason_codes`. It never contains the raw event or any
Pushover token, user key, URL, credential, exception, traceback, or path.
