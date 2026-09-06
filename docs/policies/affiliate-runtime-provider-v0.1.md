# DATA LAB Affiliate Runtime Provider v0.1

## Scope

`scripts/affiliate_runtime_provider.py` は、APIが発行したアフィリエイトURLを
Web UIの信頼済みruntime emitterへ一度だけ渡すための、非配備・外部通信なしの参照実装である。
Cloudflare Functions、DMM API、DB、Public JSON、静的artifactには接続しない。

## Delivery gate

Providerは既存のAffiliate Link Adapter v0.1とAffiliate UI Handoff v0.1へ判定を委譲する。
URL形式、Rights、lifecycle、verification、Publication Gate、PR表示のいずれかが未達なら
emitterを呼ばず `BLOCKED` とする。すべて通過した場合のみ、同期callbackへURLを一度渡す。

## Data boundary

URLは呼び出し引数とcallback引数にだけ存在し、安全な結果、ログ、例外、永続化、
Public JSON、静的artifactへ含めない。callbackの例外内容も破棄し
`REDIRECT_DELIVERY_FAILED` だけを返す。

結果はversion、status、試行・成功フラグ、production writeフラグ、reason codeに限定する。
未知version、無効callback、内部例外はfail-closedとする。

## Activation boundary

この追加だけではproduction runtimeは接続済みにならない。
Release Gate v0.6の `AFFILIATE_RUNTIME_CONNECTED=false` は維持する。
実接続はIssue #66の公式回答、runtime方式、秘密情報設定、CTA直近のPR表示、
本番smoke testが揃った別Gateで行う。
