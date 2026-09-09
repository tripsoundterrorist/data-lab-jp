# Temporal Dry Connection Contract Review v0.1

The isolated integration adapter accepts sanitized payloads, while the dry
connection harness accepts already-created v0.2 states. No public contract
currently transfers a fully validated four-population state bundle between
them.

Connecting them through the adapter's private validator would create an
unstable dependency. Re-validating the payloads in the harness would create two
validation boundaries that could diverge. Both approaches are rejected.

The next isolated Gate is `ADD_VALIDATED_STATE_BUNDLE_CONTRACT`: expose a
bounded public builder that validates all four payloads atomically and returns
states only to in-process candidate code. Safe output must remain aggregate-only.

This review performs signature inspection and existing memory-only evidence
only. It authorizes no active connection, API request, filesystem or D1 write,
baseline activation, migration, deployment, route activation, publication, or
affiliate eligibility change.
