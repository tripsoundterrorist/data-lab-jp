# DATA LAB Affiliate Route Deployment Review v0.1

## Purpose

Cloudflare Pagesのaffiliate routeを配備する前に、候補チェーン、binding、runtime、
privacy、rollback、Free plan境界をsanitized booleanだけで確認する。
このreviewはコード配備、route作成、API疎通、affiliate有効化、公開を行わない。

## 2026-09-12 review

確認済み：

- D1 lookup 861件、enabled 0件、runtime eligible 0件
- D1 binding名
- production secret binding名2件（値は未参照）
- 現行Workers型定義上のD1およびRate Limit binding API
- 既存candidate chainが`runtime-candidates/`に隔離されていること
- production Pages Function entrypointが存在しないこと

未完了：

- Pages Function entrypoint
- Rate Limiting bindingの設定
- request/IP/headerを直接保存しない匿名client key生成境界
- Workers上で動作するserver-side DMM provider
- CTA直近のPR表示との接続
- route rollback手順

## Fail-closed boundary

全項目が揃っても`READY_FOR_SEPARATE_DEPLOYMENT_APPROVAL`までとし、
`production_deployment_allowed=false`、`route_activation_allowed=false`、
`affiliate_activation_allowed=false`、`paid_plan_change_allowed=false`を維持する。

課金またはFree plan変更が必要になった場合は停止してoperatorへ通知する。
credential、secret、URL、account/database ID、商品ID、raw requestは入力・出力しない。
