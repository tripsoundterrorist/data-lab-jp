# Notification Ledger Mixed Read Compatibility v0.2

## Scope

Ledger reader and read-only Recovery diagnostics accept valid snapshots composed
of v0.1 records, v0.2 records, or both. Recovery reports the exact detected class
as `0.1`, `0.2`, or `MIXED_0.1_0.2`.

The existing writer remains v0.1-only. `record_success()` still creates the exact
five-field v0.1 record and never invents an incident identity. Existing v0.1 or
v0.2 records are retained byte-equivalent at the record level when a later v0.1
success is appended.

## Fail-closed compatibility

Exact event identity remains unique across all versions. Invalid v0.2 incident
identity, unknown version, malformed or extra fields, invalid timestamps,
duplicate exact identities, duplicate JSON keys, missing newline, oversized
files, locks, and temporary artifacts keep their existing corruption or manual
review behavior.

## Preserved boundaries

No migration, bootstrap, v0.2 write, existing-record rewrite, incident lookup,
noise-control integration, send, retry, credential, Queue, production, or LIVE
activation is added. Atomic replacement, lock, capacity, and recovery semantics
remain unchanged.

The next independent Gate may add an explicit v0.2 success-write method. The
current `record_success()` must remain v0.1-only until that Gate is reviewed.
