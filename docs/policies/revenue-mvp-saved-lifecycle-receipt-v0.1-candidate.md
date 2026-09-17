# Revenue MVP Saved Lifecycle Receipt v0.1 Candidate

Status: local validation only. Production publication remains closed.

The generator reads the existing SQLite database in read-only/query-only mode
and creates exactly one sanitized receipt for every stored public item. The
packet may contain only public ID, sanitized `VerificationObservation`,
inventory signal, freshness boolean, observation time, and bounded reason
codes. Generated packet files are permitted only outside the repository.

The current saved collection schema does not retain proof of an exact
single-item lookup or whether a safe affiliate link was present. Collection
presence must not be upgraded into affiliate eligibility. Consequently, saved
rows generate `UNKNOWN` observations with affiliate state unknown and yield
zero candidates. Missing, duplicate, stale/future, identity, timestamp, and
item-binding anomalies fail closed.

A future live verification must be separately authorized and bounded to an
exact expected item lookup. It must classify the response through
`product_verification`, retain only the sanitized observation contract, bind
its observation time to the public item observation, and discard request URLs,
credentials, API/affiliate IDs, content IDs, affiliate URLs, and raw bodies.

This candidate performs no API call, secret read, database write, D1 access,
deployment, route/scheduler activation, CTA change, production publication, or
Gate mutation.
