# Temporal Series Pipeline Connection Review v0.1

Status: connection design required; direct connection is not authorized.

The isolated v0.2 integration adapter cannot safely replace or enter the active
chain. The active runner accepts no explicit `series_id`, the active state and
store use the legacy identity, and the active adapter enters a non-dry-run write
path. A partial substitution could compare across series or persist an
incompatible state.

The safe implementation order is:

1. implement an isolated v0.2 state-store candidate;
2. implement an isolated v0.2 runner candidate;
3. verify legacy documents remain read-only during discovery;
4. verify filenames and comparison identity are series-aware; and
5. add a dry-run-only connection harness.

Each step requires tests and a separate review. This review performs source and
signature introspection only. It authorizes no active connection, API request,
state write, history migration, baseline activation, deployment, or production
route change.
