# DATA LAB Affiliate Release Gate State v0.1

## Purpose

The Revenue MVP release report distinguishes the reviewed, non-deployed DMM
pipeline from a production runtime connection.

## States

- `affiliate_pipeline_ready=true` means the inert pipeline module has the
  reviewed version and callable entry point.
- `affiliate_integration_allowed=true` means a separately reviewed production
  runtime route is connected. It remains false in the current repository.

Pipeline readiness never permits publication, API activation, redirect
delivery, or deployment. The release remains blocked until the independent
official-answer, public-data, publication, production-smoke, Search Console,
and production runtime conditions all pass.

## Fail-closed behavior

An unknown pipeline version or non-callable entry point reports
`affiliate_pipeline_ready=false`. Internal evaluation errors return the bounded
release-gate failure result with both affiliate state fields false.

## Current next action

The connector and inert pipeline already exist. The remaining technical action
is `IMPLEMENT_AFFILIATE_RUNTIME_ROUTE`; its design, secrets, deployment, and
activation require separate review and approval.
