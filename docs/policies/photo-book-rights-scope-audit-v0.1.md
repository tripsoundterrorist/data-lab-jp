# 写真集field rights範囲監査 v0.1

更新日: 2026-10-02 JST

## 目的

既存Rights Decision Matrixの項目を、将来の`DMM.com / ebook / photo / photo_book` projectionへ再利用できる候補、写真集固有の公式確認が必要な項目、既存判断で禁止されている項目へ分離する。

既存の`APPROVED`は問い合わせ時の記載scopeに基づく。写真集への適用範囲をこの監査から推測せず、公開許可ではなく再利用候補に留める。

## 再利用候補

- title
- 商品ページURL
- series
- genre
- current price
- review count
- review average

## 個別確認が必要な項目

- release date
- list price
- observation timeとfreshness表示
- `actor` roleの正式な意味と表示可否
- `author` roleの正式な意味と表示可否
- `manufacture` roleの正式な意味と表示可否
- 写真集への既存rights回答の適用範囲

role labelを出演者、著者、出版社、メーカー、ブランド等へ変換しない。異なるカテゴリのentityと自動統合しない。

## 禁止を維持する項目

- DMM Books商品画像
- product description
- user review text
- raw API response

Rights Decision Matrixでは、FANZA対象商品画像の許可をDMM Books画像へ一般化しないことが明示され、`dmm_books_product_image`は`PROHIBITED`である。この判断が正式に更新されない限り、写真集画像は表示候補へ含めない。

## 安全境界

監査結果は`READY_FOR_PHOTO_BOOK_COMPLIANCE_SCOPE_REVIEW`に留める。field rights、画像表示、contributor semantics、公開、affiliate、Production、Publication Gateはすべて未承認のままとする。
