# 電子コミックfield rights範囲監査 v0.1

更新日: 2026-10-02 JST

## 目的

既存Rights Decision Matrixの項目を、将来のFANZA電子コミックprojectionへ再利用できる候補と、電子コミック固有の公式確認が必要な項目へ分離する。

既存の`APPROVED`は問い合わせ時の記載scopeに基づく。電子コミックへの適用範囲をこの監査から推測せず、すべて「再利用候補」に留める。

## 再利用候補

- title
- FANZA対象商品のmain image
- 商品ページURL
- series
- genre
- current price
- review count
- review average

再利用候補は公開許可ではない。特に画像はDMM Books画像への一般化が明示的に禁止されているため、FANZAの`ebook_comic` API画像が既存回答の「FANZA対象商品メイン画像」に含まれるかを別途確認する。

## 個別確認が必要な項目

- release date
- list price
- observation timeとfreshness表示
- `author`役割の意味と表示可否
- `manufacture`役割の意味と表示可否
- 電子コミックへの既存rights回答の適用範囲

役割キーだけを根拠に作者・出版社・メーカーへ名称変換しない。異なるカテゴリとのentity統合もしない。

## 禁止を維持する項目

- product description
- user review text
- raw API response

## 安全境界

監査結果は `READY_FOR_EBOOK_COMIC_COMPLIANCE_SCOPE_REVIEW` に留める。field rights、画像scope、contributor semantics、公開、affiliate、Production、Publication Gateはすべて未承認のままとする。
