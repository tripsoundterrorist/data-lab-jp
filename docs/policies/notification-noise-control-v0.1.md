# Notification Noise Control v0.1

## Scope

This pure policy reduces repeated mobile notifications without changing the
existing Adapter, Sender, Ledger, Runtime, LIVE state, or event mappings. It
accepts only a sanitized 64-hex stable event key and timezone-aware timestamps;
it never receives message text, credentials, raw errors, or payloads.

## Delivery rules

- The first or a distinct `JOB_WAITING_APPROVAL`, `JOB_FAILED_SAFE`, or
  `QUEUE_BLOCKED` remains immediate.
- An identical approval event may remind after 30 minutes.
- An identical failed-safe or queue-blocked event may remind after one hour.
- Identical `JOB_COMPLETED` events remain suppressed; distinct completions
  remain normal delivery.
- `CRITICAL_STOP` returns `PRESERVE_CRITICAL`; existing emergency-send blocking
  and priority semantics are unchanged and cannot be downgraded here.

Only an exact event-key match is considered a duplicate. Different incidents
are never suppressed by timing alone. The reminder boundary is inclusive.

## Fail-closed and integration boundary

Unknown event types, malformed keys, naive/invalid timestamps, incomplete prior
delivery evidence, and time regression return `INVALID_INPUT / NONE` with no
delivery. The policy performs no I/O, notification send, ledger write, retry,
sleep, scheduling, checkpoint, Queue, production, or LIVE action.

Runtime integration requires a separate Gate proving a sanitized stable event
key and durable prior-delivery evidence. Until then this policy is evaluation
only and current notification behavior remains unchanged.
