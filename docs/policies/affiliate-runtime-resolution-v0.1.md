# DATA LAB Affiliate Runtime Resolution v0.1

## Scope

`scripts/affiliate_runtime_resolution.py` は、公開商品IDから内部content IDを解決し、
DMM APIの単一商品応答からアフィリエイトURL候補を取り出し、
Affiliate Runtime Provider v0.1へ一時的に渡すread-only統合契約である。

DB接続、HTTP通信、Cloudflare配備、秘密情報読込は実装せず、すべて信頼済みcallbackへ依存注入する。

## Fail-closed order

Publication Gate、Rights、lifecycle、verification、PR表示、公開ID形式、callback形式を
最初に検証する。一つでも未達なら、商品ID解決、API要求、redirect配信を実行しない。

通過後のみ次の順序で処理する。

1. 公開IDを内部content IDへ解決
2. content IDを使って単一商品API応答を取得
3. 応答statusと一致するitemが一件だけであることを確認
4. `affiliateURL` 候補を既存Runtime Providerへ渡す
5. Providerが許可した場合だけ信頼済みemitterへ一度配信

未解決、0件、複数一致、フィールド欠落から販売可否やアフィリエイト対象可否を推測しない。

## Data boundary

公開ID、内部content ID、アフィリエイトURL、API応答、callback例外はsafe resultへ含めない。
結果はversion、status、各段階の試行・成功フラグ、production writeフラグ、
決定済みreason codeに限定する。

## Activation boundary

テストでは予約済みダミードメインのみを使用する。この契約だけでは実runtime接続済みとせず、
Release Gate v0.6の `AFFILIATE_RUNTIME_CONNECTED=false` を維持する。
公式回答、実DMM応答確認、Cloudflare方式、秘密情報設定、PR表示、本番smokeは別Gateとする。
