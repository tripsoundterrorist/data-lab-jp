# DATA LAB Affiliate Runtime DMM Pipeline v0.1

## Scope

This inert composition connects the read-only DMM connector callbacks to the
existing guarded affiliate runtime resolver. It has no CLI, web route, server,
deployment configuration, scheduler, or production activation.

## Evaluation order

Rights, lifecycle, verification, Publication Gate, PR disclosure, public ID,
and callback shape are evaluated by the resolver before either connector
callback runs. In the current fail-closed state, no database lookup, DMM
request, or redirect delivery is attempted.

Only a future state in which every existing guard is explicitly satisfied can
perform the read-only public-ID lookup and one-item API request. The resulting
affiliate URL remains memory-only and can reach only the trusted synchronous
emitter after the existing adapter and UI handoff both approve it.

## Validation

CI uses a temporary SQLite database, dummy credentials, an in-memory dummy API
response, and an inert approved-host fixture URL. Tests confirm:

- closed Gate stops before database and API callbacks;
- pending lifecycle stops before callbacks;
- a future eligible fixture traverses the full pipeline once;
- an unapproved host never reaches the emitter;
- safe results never contain the URL;
- the database remains byte-identical.

## Activation boundary

This module does not change Issue #66, rights, lifecycle, verification,
publication, affiliate integration, or production deployment gates. A deployed
route and real runtime invocation require separate review and approval.
