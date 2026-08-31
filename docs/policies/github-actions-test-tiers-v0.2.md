# GitHub Actions Test Tiers v0.2

## Purpose

This Gate connects the proven test-tier entry points to GitHub Actions while
preserving the v0.1 CI security, cost, and coverage boundaries.

## Event flow

- Every pull request and push to `main` runs FAST first.
- A FAST failure prevents the broader validation job from starting.
- Pull requests compile all Python sources and run REGRESSION.
- Pushes to `main` run FULL, which compiles all Python sources before running
  the complete regression suite.

The PR path therefore retains the v0.1 `compileall` plus complete unittest
coverage. The main path receives the same coverage through FULL. New
`tests/test_*.py` files remain automatically included.

## Safety and cost boundary

The workflow remains limited to pull requests and pushes to `main`, grants only
`contents: read`, uses pinned credential-free checkout and standard
`ubuntu-latest`, and keeps five-minute timeouts and concurrency cancellation.
It adds no schedule, manual trigger, secret, dependency install, cache,
artifact, deployment, release, write permission, larger runner, or paid
service. Repository visibility changes still require cost review before CI
expansion.

LIVE state, approval boundaries, queue/executor/notification writes, blocked
checkpoint behavior, operational-task priority, and usage protection are not
changed.

## Next Gate

After both a pull-request REGRESSION run and a post-merge FULL run succeed, the
next small Gate may connect checkpoint metadata to commit/push and CI evidence.
