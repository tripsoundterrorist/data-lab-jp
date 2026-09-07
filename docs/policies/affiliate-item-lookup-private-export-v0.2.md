# DATA LAB Affiliate Item Lookup Private Export v0.2

## Identity binding

The exporter requires the exact lowercase SHA-256 established by the approved
read-only export preflight. Missing, malformed, or mismatched identity fails
closed before an output directory or file is created.

The source digest is checked before opening SQLite and again after the bounded
item query. A change during the read returns
`DATABASE_CHANGED_DURING_EXPORT` and creates no SQL candidate. Symbolic-link
sources are rejected.

## Execution boundary

The command-line entry point accepts only `--db` and `--expected-sha256`. Its
output is fixed to the Git-ignored `runtime/private/affiliate-item-lookup.sql`.
An existing target is never overwritten. SQLite remains `mode=ro` with
`PRAGMA query_only = ON`.

The safe JSON result adds `database_identity_verified` but never returns the
source digest, database path, public ID, content ID, URL, SQL, or credentials.
All generated rows still rely on the schema's pending and disabled defaults.

Running this command against the real database requires explicit approval.
D1 creation or import, candidate inspection or transfer, eligibility changes,
runtime binding, deployment, and publication remain separate fail-closed Gates.
Issue #66 remains open.
