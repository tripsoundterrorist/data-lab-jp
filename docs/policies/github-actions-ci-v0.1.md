# GitHub Actions CI Contract v0.1

## Purpose and scope

This Gate adds one baseline CI workflow for pull requests and pushes to `main`.
It compiles Python sources and runs the existing complete unittest discovery.
It does not deploy, publish, write repository contents, use secrets, upload
artifacts, populate caches, or trigger LIVE behavior.

## Cost boundary

The repository was verified public before this Gate. GitHub documents standard
GitHub-hosted runners as free for public repositories. This workflow therefore
uses only `ubuntu-latest`; larger runners and custom images are prohibited.
Artifacts and caches are omitted to avoid storage billing exposure.

If repository visibility changes to private, or a larger/custom runner becomes
necessary, CI expansion must stop until plan minutes and possible charges are
reviewed and approved. This Gate authorizes no paid service.

## Security and resource controls

The workflow grants only `contents: read`. Checkout is pinned to the full
actions/checkout v7.0.1 commit SHA, uses depth one, and does not persist Git
credentials. Runs have a five-minute timeout. Concurrency cancels superseded
runs for the same workflow/ref. There are no scheduled or manual triggers,
third-party dependencies, package installs, network downloads, secrets,
artifacts, caches, deployment steps, or write permissions.

## Test boundary

CI runs `compileall` followed by the existing full unittest discovery. This is
the initial baseline only; it does not yet redefine FAST, REGRESSION, or FULL.
The next independent efficiency Gate may classify tests while preserving this
baseline until the new tiers are proven equivalent.

## Existing safety rules

Fail-closed behavior, approval Gates, LIVE-disabled state, blocked checkpoint
handling, safe-task switching, Collector/Backup/Stale Check priority, and usage
limit protection remain unchanged.
