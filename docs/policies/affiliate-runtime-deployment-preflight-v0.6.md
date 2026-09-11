# DATA LAB Affiliate Runtime Deployment Preflight v0.6

## Change from v0.5

Cloudflare Pages production環境で必要なsecret binding名2件がencrypted状態で存在することを
値を読まずに確認し、names-only Gateを通じて`current_input()`へ反映した。
これにより`SECRET_BINDINGS_NOT_READY`を解消した。

## Remaining blockers

- `/go/:public_id` routeは未配備
- bounded per-client rate limitは未配備
- log redactionとresponse cache policyは未配備
- runtime provider/resolution chainは未接続
- CTA直近のPR表示は未接続

したがってpreflightは`BLOCKED`、`production_deployment_allowed=false`のままである。
secretの存在だけでは値の正当性やAPI疎通を証明せず、deploy、affiliate有効化、公開、
paid plan変更を許可しない。
