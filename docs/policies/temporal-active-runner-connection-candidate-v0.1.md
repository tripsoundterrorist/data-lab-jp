# Temporal Active Runner Connection Candidate v0.1

Status: isolated test-only implementation candidate. It is not connected to the
active runner.

The candidate accepts one exact validated four-population bundle. It first uses
the memory-only dry connection harness for every population. Only after all four
assessments succeed may it pass the unchanged bundle to an injected
`IsolatedTemporalStateStore` constructed through its test factory.

An invalid bundle, population mismatch, failed comparison, or invalid store
stops fail-closed. A dry assessment failure occurs before the persistence call.
Partial or uncertain persistence returns recovery-required without unsafe retry
or rollback. The legacy runner and its `dry_run=False` adapter path are never
used.

The implementation may write only to a caller-created isolated test directory.
It authorizes no active-runner connection, API request, production write,
scheduler change, deployment, publication, D1 operation, or affiliate change.
Promotion requires a separate evidence review and explicit approval.
