# Temporal Validated Bundle Dry Connection v0.1 Candidate

This isolated connector accepts only the public `ValidatedSeriesStateBundle`
produced by `build_validated_series_state_bundle` and passes its four-state tuple
to the existing dry connection harness in memory. It does not rebuild payloads,
call the bundle builder, use private validators, or duplicate payload/state
validation. State content and fixed population ordering remain owned by the
existing harness contract.

The connector validates only the public bundle envelope: exact type and fields,
adapter version, successful atomic validation, four-state count, fixed success
reason, and false active-pipeline, API, and write authorization flags. Missing,
failed, modified, contradictory, or unknown-version envelopes fail closed before
the harness is called. Invalid, blocked, permissive, or unknown harness results
also fail closed with fixed reason codes.

Success is `VALIDATED_BUNDLE_DRY_CONNECTION_COMPLETE` with reason
`VALIDATED_BUNDLE_CONNECTED_TO_DRY_HARNESS`. Output contains only bounded status,
counts, non-authorization flags, and the harness's existing safe summary. It
contains no series ID, content ID, payload, path, credential, raw exception, or
state object.

This Gate performs no active pipeline connection, collection, API request,
filesystem or D1 access, state write, schema migration, baseline activation,
deployment, route activation, publication, or affiliate eligibility change.

## Next Gate

The isolated memory-only bundle-to-harness contract is complete. Any connection
to an active pipeline, filesystem-backed state, collection API, scheduler,
publication flow, or production route requires a separate explicit review and
must remain blocked until that Gate is approved.
