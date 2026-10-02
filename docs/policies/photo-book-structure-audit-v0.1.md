# 写真集構造監査 v0.1

更新日: 2026-10-02 JST

## 目的

隔離カテゴリDBの`photo_book`を読み取り専用で匿名監査し、次のカテゴリ準備を開始できる構造か確認する。

固定source namespaceは `DMM.com / ebook / photo / photo_book` である。FANZA電子コミックやDMM Booksの他floorへ意味・権利・entityを一般化しない。

## 集計項目

- 商品数と最新スナップショット数
- title、release date、商品URL、HTTPS画像
- series、genre
- current price、list price、discount
- review平均・件数が両方存在する商品数
- contributor role別の商品数、entry数、完全・不完全entry数
- JSONまたはentity構造が不完全な商品数

商品ID、タイトル、URL、画像URL、価格、review値、entity ID・nameは出力しない。

## entity境界

観測された`actor`、`author`、`manufacture`等のrole labelは別々に保持する。出演者、著者、出版社、メーカー、ブランド等の正式な意味や表示可否をこの監査から推測しない。

## 安全境界

結果は`READY_FOR_PHOTO_BOOK_STRUCTURE_REVIEW`に留める。次はすべてfalseである。

- entity semantics確認
- field rights確認
- Compliance承認
- DB書き込み
- publication artifact生成
- 公開・affiliate・sitemap
- Production書き込み

構造監査成功だけでは、写真集の公開・画像利用・収益化を許可しない。
