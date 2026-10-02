# 写真集非公開projection候補 v0.1

更新日: 2026-10-02 JST

## 目的

`DMM.com / ebook / photo / photo_book`の実データ構造に基づき、将来の非公開projectionで使用し得る項目の厳格な構造だけを検証する。field rights、entity semantics、Compliance、公開は承認しない。

## 固定source namespace

- site: `DMM.com`
- service: `ebook`
- floor: `photo`
- content type: `photo_book`
- public ID候補: `pbk_`と24桁の小文字16進数
- 商品URL host: `book.dmm.com`

他カテゴリ、FANZA、DMM Booksの別floorとnamespaceを共有しない。

## 候補フィールド

- title、release date
- current price、optional list price
- `actor`、`author`、`manufacture`の独立参照配列
- series
- optional genre配列
- 商品ページURL
- review averageとreview count
- observation time、freshness候補

## 明示的な除外

写真集projectionは画像フィールドを持たない。Rights Decision Matrixで禁止されているDMM Books商品画像を、URLの取得可否にかかわらず候補へ含めない。

完全allowlistにより、画像、商品説明、review本文、raw response、affiliate URL、query context、未知フィールドを拒否する。

`actor`、`author`、`manufacture`は別配列として保持し、公式回答前に人物、著者、出版社、メーカー、ブランド等へ意味変換しない。

## 安全境界

構造検証成功は`READY_FOR_FIELD_AND_SEMANTICS_REVIEW`に留める。次はすべてfalseである。

- contributor semantics確認
- field rights確認
- Compliance承認
- 公開許可
- affiliate有効化
- sitemap変更
- Production書き込み

validatorはAPI、DB、ファイル、Publication Gateへ接続しない。
