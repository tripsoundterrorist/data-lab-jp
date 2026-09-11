# DATA LAB Affiliate Runtime Deployment Preflight v0.5

## Change from v0.4

Cloudflare Pages production secretのnames-only evidence Gateを`current_input()`へ接続した。
2026-09-11のread-only確認ではproduction secretが0件のため、secret bindingは未設定として
`SECRET_BINDINGS_NOT_READY`を維持する。

secret値は入力・取得・出力せず、必要なbinding名2つが完全一致した場合だけpreflightへ渡す。
未知名、重複名、未確認、値非参照境界の不成立はfail-closedとする。

## Current state

- D1 lookup/data binding: ready for inert review
- production secret bindings: blocked
- route/rate limit/log redaction/cache policy: not deployed
- runtime chain: not connected
- proximate PR disclosure: not connected

`production_deployment_allowed=false`を維持し、secret登録、deploy、affiliate有効化、公開、
paid plan変更は別承認とする。
