# Notification Ledger Record Contract v0.2

## Scope

This pure codec defines future notification Ledger v0.2 records without reading,
writing, migrating, or replacing the current Ledger. A v0.2 record adds one
field, `incident_identity`, to the existing success-only record. Both exact event
and incident identities are lowercase 64-hex values.

## Backward compatibility

Mixed snapshots containing exact valid v0.1 and v0.2 records are accepted.
Exact `event_identity` must remain unique across all versions. Existing v0.1
records are never rewritten, upgraded, or treated as incident evidence because
their incident identity cannot be reconstructed safely.

The read-only evidence function returns the latest UTC delivery timestamp only
from matching v0.2 records. A v0.1-only snapshot returns `NO_V02_EVIDENCE`, not
an inferred delivery. Invalid records, duplicate exact identities, malformed
snapshots, or invalid lookup identities fail closed.

## Preserved boundaries

This Gate performs no JSON/file I/O, Ledger transaction, lock, migration,
delivery, retry, Runtime integration, notification, Queue, production, or LIVE
action. Current Ledger v0.1 parser and persistence remain unchanged.

Future persistence integration must be additive, preserve atomic replacement and
corruption blocking, and must never rewrite existing v0.1 records merely to add
an incident identity.
