# DATA LAB Affiliate D1 Production State v0.1

## Purpose

2026-09-13にoperator確認とCloudflare D1のread-only query/exportで確認した、
アフィリエイトlookupのsanitized production stateをpreflightへ渡す。

## Confirmed state

- Cloudflare Free plan
- `AFFILIATE_ITEM_LOOKUP` binding名
- tableとeligible viewが存在
- lookup 867件
- pending 867件
- enabled 0件
- runtime eligible 0件
- private candidate 867件との全mapping一致

database ID、account ID、credential、secret、URL、商品ID、SQL payload、raw exportは
入力・出力・Git管理対象にしない。

## Boundary

結果が`READY_FOR_INERT_RUNTIME_REVIEW`でも、Cloudflare write、paid plan変更、
route配備、runtime接続、affiliate有効化、公開、Publication Gate解除は許可しない。
課金またはplan変更が必要になった場合は停止し、operatorへ通知する。

件数不一致、enabled/eligible行、pending不一致、mapping未確認、型不正はfail-closedとする。
