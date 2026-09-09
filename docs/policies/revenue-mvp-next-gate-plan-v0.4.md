# Revenue MVP Next Gate Plan v0.4

The next-gate plan now consumes the read-only temporal continuation assessment
and isolated series-candidate evidence in addition to lifecycle and sort
evidence.

When all of the following exact conditions hold, the unsafe direct
`CONTINUE_TEMPORAL_OBSERVATION` action is replaced with
`IMPLEMENT_ISOLATED_TEMPORAL_SERIES_PIPELINE_INTEGRATION`:

- all four saved populations are outside the existing comparison window;
- a fresh-baseline policy is required;
- the isolated series candidate passes all seven implementation checks;
- the candidate remains disconnected from the active pipeline;
- API request, state write, and baseline activation remain unauthorized.

This derived action authorizes local candidate implementation and tests only.
It does not authorize migration, filesystem integration, API communication,
state persistence, baseline activation, history reset, collection, or
publication. Non-long-gap states retain the existing temporal observation
action. Malformed, unknown, version-mismatched, or permissive evidence fails
closed.

The plan remains `BLOCKED` with `production_release_allowed=false`. Official
lifecycle and sort confirmation remain separate external-boundary actions.
