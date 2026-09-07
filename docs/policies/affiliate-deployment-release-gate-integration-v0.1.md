# DATA LAB Affiliate Deployment / Release Gate Integration v0.1

## Purpose

The Revenue MVP release report now includes the existing non-deploying
affiliate runtime deployment preflight. This makes route prerequisites visible
in the same bounded report as publication, official-answer, Search Console, and
production-smoke state.

## Reported safe fields

- preflight status;
- deployment-candidate boolean;
- dedicated route configuration boolean;
- bounded rate-limit configuration boolean;
- predefined reason codes and next actions.

Secret values, DMM response data, affiliate URLs, item identifiers, request
URLs, and exception details are never accepted or returned by this integration.

## Release condition

`READY_FOR_RELEASE_APPROVAL` additionally requires the deployment preflight to
be a review candidate. This does not deploy or activate anything, and
`production_release_allowed` remains false pending separate explicit approval.

The current repository remains blocked: there is no configured server-side
route, private lookup binding, secret binding declaration, rate-limit policy,
or production runtime connection, and Issue #66 remains unresolved.

## Failure behavior

Any exception while reading the preflight returns the bounded Release Gate
`FAIL_CLOSED` result. All affiliate readiness fields are false or `UNKNOWN`.
