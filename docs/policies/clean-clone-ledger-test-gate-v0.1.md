# Clean-Clone Production Ledger Test Gate v0.1

The production notification ledger is runtime state and remains excluded from
Git. Tests that assert the contents or immutability of that exact production
file run only when the formal ledger file exists.

A clean clone must report those production-artifact tests as explicitly skipped,
not failed. All isolated ledger, notification, dispatch, schema, duplicate, and
failure-safety tests continue to run in every environment. On the production
workstation, where the formal ledger exists, the gated tests continue to enforce
the approved record count, canary identity, compatibility, and read-only behavior.

The gate must never create, copy, bootstrap, repair, or mutate a production
ledger. Missing runtime state is not inferred to be healthy.
