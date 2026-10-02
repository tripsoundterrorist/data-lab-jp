# 電子コミック非公開projection候補 v0.1

更新日: 2026-10-02 JST

## 目的

FANZA電子書籍comicフロアの実データ構造に基づき、将来の公開projectionで使用し得る項目の厳格な構造契約だけを先行準備する。公式回答待ちのため、field rights、entity semantics、Compliance、公開は一切承認しない。

## 固定source namespace

- site: `FANZA`
- service: `ebook`
- floor: `comic`
- content type: `ebook_comic`
- public ID候補: `ebc_`と24桁の小文字16進数

他カテゴリやDMM Booksへnamespaceを一般化しない。

## 候補フィールド

- title、release date
- current price、optional list price
- `author`由来参照
- `manufacture`由来参照
- series、genre
- 商品メイン画像候補、商品ページURL
- review average、review count
- observation time、freshness状態

入力フィールドは完全allowlistとし、商品説明、レビュー本文、rawレスポンス、affiliate URL、query contextを受け取らない。

`author`と`manufacture`は別の参照配列として保持する。公式回答前に作者、出版社、メーカー、ブランド等へ変換せず、他カテゴリのentityとも統合しない。

## 安全境界

構造が正しくても結果は `READY_FOR_FIELD_AND_SEMANTICS_REVIEW` に留める。次は常にfalseである。

- contributor semantics確認
- field rights確認
- Compliance承認
- 公開許可
- affiliate有効化
- sitemap変更
- Production書き込み

このvalidatorはAPI、DB、ファイル、Publication Gateへ接続しない。公式回答後も自動昇格せず、別のCompliance決定とユーザー承認を必要とする。
