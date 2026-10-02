# 写真集projection準備度監査 v0.1

更新日: 2026-10-02 JST

## 目的

隔離カテゴリDBの`photo_book`各商品について、最新スナップショットから画像なしの非公開projection候補をメモリ内で組み立て、厳格な構造validatorへ適用する。

出力は対象件数、ready件数、blocked件数、固定理由コード別件数だけに限定する。商品ID、public ID、タイトル、URL、価格、review、entity値は出力せず、候補artifactも生成しない。

## 入力境界

既存カテゴリ収集健全性が`HEALTHY`である場合だけSQLite read-only modeで最新スナップショットを読む。source namespaceは`DMM.com / ebook / photo / photo_book`へ固定する。

`actor`、`author`、`manufacture`は別配列として渡し、意味変換やカテゴリ横断統合を行わない。genreはAPIで存在しない商品があるため空配列を許容する。

## 画像境界

Rights Decision Matrixの既存禁止判断に従い、収集DBに画像URLが存在していてもprojection候補へ読み込まず、出力もしない。監査結果の`image_field_included`は常にfalseである。

## 安全境界

監査結果は`READY_FOR_FIELD_AND_SEMANTICS_REVIEW`に留める。構造readyでも次はすべてfalseである。

- artifact生成
- DB書き込み
- contributor semantics確認
- field rights確認
- Compliance承認
- 公開・affiliate・sitemap
- Production書き込み

公式回答後も自動昇格せず、03 COMPLIANCE判断とユーザー承認を必要とする。
