# DATA LAB Affiliate Runtime Deployment Preflight v0.1

## Purpose

`scripts/affiliate_runtime_deployment_preflight.py` は、アフィリエイトredirect runtimeを
Cloudflareへ配備する前の候補構成を、秘密値やURLを読まずに検証する。
このpreflight自身は外部通信、binding作成、デプロイ、公開状態変更を行わない。

## Required candidate

- secret binding名：`DMM_API_ID`、`DMM_AFFILIATE_ID`、`AFFILIATE_CLIENT_KEY_SECRET`
- private item lookup binding名：`AFFILIATE_ITEM_LOOKUP`
- 専用route：`/go/:public_id`
- method：`GET`、`HEAD`のみ
- redirect：一時redirectの302
- per-client rate limit：1〜60 requests/minute
- burst：1〜10、かつrequests/minute以下
- identifier、URL、credentialのログ秘匿
- redirect response cache無効
- Issue #66の公式回答候補
- Runtime ProviderとRuntime Resolutionの接続
- CTA直近のPR/広告表示

bindingは名前だけを受け付け、値は入力にもsafe resultにも含めない。
未知名、重複名、不正形式はreadyとして扱わない。

## Result

全条件が揃っても `READY_FOR_DEPLOYMENT_REVIEW` までとし、
`production_deployment_allowed` は常にfalseとする。
2026-09-12の配備記録ではroute、rate limit、runtime chain、Worker secret名を確認済み。本番静的ビルドには明示的な`affiliate_cta_eligible` boolean境界を追加し、falseでは通常リンク、trueの場合だけPR表示と同一オリジン`/go/` CTAを同時生成する。builderの既定値はfalseである。これによりpreflightは`READY_FOR_DEPLOYMENT_REVIEW`となるが、Publication/Lifecycle/Semantics Gateは引き続き閉鎖する。記録済みの配備証跡は現在のCloudflare状態をライブ確認するものではない。

個別の不足はreason codeとnext actionで報告する。入力不正や内部例外は
`FAIL_CLOSED` とし、入力内容・秘密値・URL・識別子・例外文を返さない。

## Activation boundary

このGateはCloudflare方式の候補条件を固定するだけで、Cloudflare設定や有料機能を追加しない。
実配備は公式回答、費用対効果、custom domain影響、rollback、本番smokeを確認する別承認Gateとする。
