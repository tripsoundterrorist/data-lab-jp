# Notification Ledger Explicit v0.2 Writer

## Scope

`LedgerTransaction.record_success_v02()` explicitly appends one validated v0.2
success record containing both exact event and stable incident identities. It is
available only inside an existing writable Ledger transaction and reuses the
same lock, capacity limit, temporary file, flush, fsync, and atomic replacement
path as v0.1.

The existing `record_success()` remains unchanged and v0.1-only. Runtime still
calls only `record_success()`; this Gate does not activate v0.2 production writes.

## Idempotence and compatibility

If the exact event identity already exists in either version, the explicit v0.2
method returns `NO_CHANGE`. It never upgrades, replaces, or supplements an
existing v0.1 record. A new exact identity is built through the v0.2 codec and
returns `RECORDED` only after atomic replacement succeeds.

Invalid identities, event types, or timestamps fail before replacement.
Read-only transactions remain write-disabled. Replacement, capacity, lock, and
corruption failures retain their existing fail-closed behavior without retry or
automatic repair.

## Preserved boundaries

No migration, Runtime call-site change, notification behavior, incident lookup,
noise-control integration, retry, credential, Queue, production activation, or
LIVE send is introduced. Activating the explicit writer from Runtime requires a
separate reviewed Gate with exact event and incident identity evidence.
