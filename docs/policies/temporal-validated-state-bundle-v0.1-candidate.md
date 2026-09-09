# Temporal Validated State Bundle v0.1 Candidate

The integration adapter now exposes one public, atomic handoff from four
sanitized payloads to four validated v0.2 temporal states. All payloads and
generated states must validate before the bundle succeeds; failure returns an
empty state tuple rather than a partial bundle.

The internal states are available only to isolated candidate code. They are
excluded from the bundle representation and `safe_dict()`, which contain only
bounded status, counts, and non-authorization flags.

The contract permits a later memory-only connection to the dry harness without
calling private validators or duplicating payload validation. It authorizes no
active connection, API request, filesystem or D1 access, state write, baseline
activation, migration, deployment, route activation, publication, or affiliate
eligibility change.
