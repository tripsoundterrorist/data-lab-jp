# FANZA BL電子書籍field rights範囲監査 v0.1

更新日: 2026-10-02 JST

## 目的

既存Rights Decision Matrixの項目を、将来のFANZA BL電子書籍projectionへ再利用できる候補と、BLフロア固有の公式確認が必要な項目へ分離する。

電子コミックと同じ`ebook`サービスでも、既存回答が`FANZA / ebook / bl / ebook_bl`まで含むと推測しない。既存の`APPROVED`項目は再利用候補に留める。

## 再利用候補

- title
- FANZA対象商品のmain image
- 商品ページURL
- series
- genre
- current price
- review count
- review average

再利用候補はBLフロアの公開許可ではない。画像URLをAPIで取得できることも表示許可の根拠にしない。

## 個別確認が必要な項目

- BLフロアへの既存rights回答の適用範囲
- release date
- list price
- observation timeとfreshness表示
- `author`役割の意味と表示可否
- `manufacture`役割の意味と表示可否
- BL電子書籍API画像の表示範囲

役割キーから作者、出版社、メーカー等へ名称変換しない。電子コミックや他カテゴリとのentity統合もしない。

## 禁止を維持する項目

- product description
- user review text
- raw API response

## 安全境界

監査結果は`READY_FOR_EBOOK_BL_COMPLIANCE_SCOPE_REVIEW`に留める。field rights、画像scope、contributor semantics、Compliance、公開、affiliate、Production、Publication Gateはすべて未承認のままとする。

