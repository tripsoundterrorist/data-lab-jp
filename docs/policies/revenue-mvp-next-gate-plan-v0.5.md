# Revenue MVP Next Gate Plan v0.5

The plan now requires the isolated temporal series integration adapter to pass
as part of the read-only candidate evidence.

When the exact long-gap and eight-check evidence conditions hold, the unsafe
direct `CONTINUE_TEMPORAL_OBSERVATION` action is replaced with
`PREPARE_TEMPORAL_SERIES_PIPELINE_CONNECTION_REVIEW`.

This action permits documentation and contract review only. It does not
authorize connection to the active pipeline, schema migration, API access,
filesystem or D1 writes, baseline activation, collection, deployment, route
activation, affiliate eligibility, or publication.

The plan remains `BLOCKED` with `production_release_allowed=false`. Official
lifecycle and sort confirmation remain separate external-boundary actions.
