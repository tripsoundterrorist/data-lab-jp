# DATA LAB Affiliate Runtime Deployment Preflight v0.4

## Change from v0.3

2026-09-11に確認済みのsanitized D1 production stateを`current_input()`へ接続した。
private lookup 861件、全件pending、enabled 0件、runtime eligible 0件、candidateとの
全mapping一致、およびFree plan確認が揃う場合に限り、lookup preflightとdata bindingを
readyとして扱う。

## Current blockers

- production secret binding名が未確認
- `/go/:public_id` routeは未配備
- bounded per-client rate limitは未配備
- log redactionとresponse cache policyは未配備
- runtime provider/resolution chainは未接続
- CTA直近のPR表示は未接続

したがって全体は`BLOCKED`、`production_deployment_allowed=false`を維持する。
D1 readinessだけでdeploy、route、affiliate row、Publication Gateを有効化しない。

## Cost boundary

このpreflightはFree plan互換のsanitized evidenceだけを受け取る。有料機能、課金、
plan変更は許可せず、必要になった場合は作業を停止してoperatorへ通知する。
