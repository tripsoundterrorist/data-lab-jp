# Notification Suppression Metrics v0.1

Status: pure read-only metrics Gate; MOCK results only.

This contract accepts a bounded list of already-sanitized `RuntimeResult`
objects from `MOCK_RUNTIME`. It counts samples, successful deliveries,
suppressed notifications, delivered reminders, failed-safe outcomes, and
blocked emergency sends. Empty input produces explicit zero metrics.

Every result must use the current Runtime version, a known event type, sanitized
reason-code shape, and a non-contradictory status/flag combination. Unknown,
LIVE, DRY_RUN, oversized, malformed, or contradictory input blocks the complete
snapshot. Reminder classification is valid only on a successful delivery.

Output contains counts and fixed reason codes only. It never exposes event
content, notification text, timestamps, identities, credentials, transport
responses, paths, arbitrary input reasons, or exceptions. Inputs are not
mutated.

The contract performs no I/O and does not change reminder windows, suppression
decisions, Runtime, Runner, Ledger, Queue, Executor, Scheduler, Production,
LIVE, or delivery behavior.
