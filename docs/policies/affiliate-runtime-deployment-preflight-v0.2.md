# DATA LAB Affiliate Runtime Deployment Preflight v0.2

## Change from v0.1

The preflight now distinguishes a reviewed, non-deployed platform adapter
candidate from an installed route. The current repository contains the inert
Cloudflare candidate under `runtime-candidates/`, so
`platform_adapter_candidate=true` while route, binding, rate-limit, runtime,
official-answer, and production states remain blocked.

## Evaluation

A deployment review candidate requires all v0.1 conditions plus an explicit
platform adapter candidate. If it is absent, the preflight reports
`PLATFORM_ADAPTER_CANDIDATE_NOT_READY` and
`PREPARE_NON_DEPLOYED_PLATFORM_ADAPTER`.

The Revenue MVP release report exposes this state separately as
`affiliate_platform_candidate_ready`. Neither field authorizes moving code into
`functions/`, creating D1 or secrets, importing private data, deploying a
handler, or enabling redirects.

## Current boundary

The adapter candidate is ready for further local validation only. The current
route remains unconfigured and `production_deployment_allowed` remains false.
Issue #66 and all publication and production gates remain fail-closed.
