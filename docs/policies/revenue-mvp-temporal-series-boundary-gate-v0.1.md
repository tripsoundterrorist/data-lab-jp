# Revenue MVP Temporal Series Boundary Gate v0.1

The current temporal state schema and runner identify history only by site,
service, floor, sort, offset, and hits. They have no observation-series
boundary. Consequently, an observation after a long gap cannot safely become a
new baseline while prior history remains discoverable.

`scripts/revenue_mvp_temporal_series_boundary_gate.py` records the bounded
changes required before a fresh-series implementation can be considered:

- add a series identifier to the versioned state schema;
- include it in comparison identity;
- preserve explicit legacy-state readability;
- forbid cross-series comparison;
- require an explicit new-series start.

The Gate does not implement or approve these changes. Partial implementation
fails closed. Every result keeps API request, state write, and history reset
authorization false. Old states must not be deleted, overwritten, renamed, or
silently excluded.

This Gate performs no API request, filesystem mutation, database access,
publication, deployment, D1 write, eligibility change, secret operation, or
affiliate activation.
