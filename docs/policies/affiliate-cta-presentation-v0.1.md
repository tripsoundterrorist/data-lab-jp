# DATA LAB Affiliate CTA Presentation v0.1

## Purpose

`scripts/affiliate_cta_presentation.py` は、Affiliate UI Security Policyの結果から
CTAと直近PR表示の可視性・固定文言・必須rel属性を作る、URL非依存の表示契約である。

## Atomic visibility

CTAとPR表示は常に同時に表示または同時に非表示とする。

- upstreamが `UI_SECURITY_PASS` かつ `render_allowed=true`
- PR表示必須
- 外部サイト表示必須
- `noopener`、`noreferrer`、`sponsored` 必須
- 検出済みダークパターンなし

すべて満たす場合だけ `CTA_READY` とする。一つでも未達ならCTA、PR文言、
外部表示、rel属性を返さず `CTA_HIDDEN` または `INVALID_INPUT` とする。

## Wording

CTA：

> 公式商品ページを見る（外部サイト）

直近表示：

> PR：このリンクはアフィリエイトリンクです。リンク先で購入された場合、DATA LABが報酬を受け取ることがあります。

「購入可能」「対象商品」「セール中」など、未確認のavailability、purchasability、
affiliate eligibilityは表示しない。

## Data boundary

この契約はURL、公開ID、content ID、商品情報、credentialを受け取らず返さない。
実DOM、redirect、外部通信、公開状態を変更しない。

## Activation boundary

現在のRuntime/Publication Gateは閉じているため、本番UIへCTAを追加しない。
この表示契約を実UIへ接続する作業は、Issue #66の回答とruntime chain検証後の別Gateとする。
