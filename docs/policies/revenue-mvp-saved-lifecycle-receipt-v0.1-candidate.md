# Revenue MVP Saved Lifecycle Receipt Contract v0.2 Candidate

Status: local validation only. Production publication remains closed.

`LifecycleReceipt` and its packet use version `0.2`. Earlier packet versions
are rejected rather than silently interpreted with the expanded observation
semantics.

The generator reads the existing SQLite database in read-only/query-only mode
and creates exactly one sanitized receipt for every stored public item. The
packet may contain only public ID, sanitized `VerificationObservation`,
inventory signal, freshness boolean, observation time, and bounded reason
codes. Generated packet files are permitted only outside the repository.

Legacy collection snapshots do not retain a sanitized affiliate-link
observation and must not be upgraded into affiliate eligibility. They continue
to generate `UNKNOWN` observations. A snapshot written with the additive
`item_lifecycle_observations` contract may generate `API_ITEM_VISIBLE` only
when the observation is bound one-to-one to that exact latest snapshot, the
stored observation time matches, the response status is the allowlisted 200,
the snapshot identity match is true, and the affiliate URL has been reduced to
the tri-state presence observation. Missing, duplicate, stale/future,
identity, timestamp, and item-binding anomalies fail closed.

The lifecycle table never stores an affiliate URL, content identifier,
request URL, provider payload, credential, or raw exception. Existing rows are
not backfilled because their discarded response fields cannot be reconstructed
safely. Inventory remains `UNKNOWN`; no source-field mapping is inferred.

A future live verification must be separately authorized and bounded to an
exact expected item lookup. It must classify the response through
`product_verification`, retain only the sanitized observation contract, bind
its observation time to the public item observation, and discard request URLs,
credentials, API/affiliate IDs, content IDs, affiliate URLs, and raw bodies.

This candidate performs no API call, secret read, database write, D1 access,
deployment, route/scheduler activation, CTA change, production publication, or
Gate mutation.
