# Notification Incident Identity v0.1

## Scope

This Gate adds a pure stable identity for already validated notification events.
It canonicalizes every validated event field except `occurred_at` and returns the
lowercase SHA-256 digest. The existing exact `event_identity`, Ledger records,
Runtime processing, Adapter, Sender, and delivery behavior are unchanged.

## Semantics

Two otherwise identical events at different times share an incident identity.
Changes to subject, queue/job identity, event type, state, approval flag,
severity, job type, or summary code produce a different identity. Both legacy
v0.1 and typed v0.2 job/queue events delegate to existing event validation before
hashing. Invalid events return no identity.

The digest is an opaque deduplication key, not authentication, authorization, or
proof that an event was delivered. It contains no message text, credentials,
raw errors, or payload.

## Preserved boundaries

The helper performs no I/O, Ledger access, notification send, retry, scheduling,
Queue mutation, production action, or LIVE activation. It is not yet consumed by
Runtime or persisted by Ledger.

The next Gate must define read-only durable delivery evidence keyed by incident
identity without rewriting v0.1 records or weakening corruption handling.
