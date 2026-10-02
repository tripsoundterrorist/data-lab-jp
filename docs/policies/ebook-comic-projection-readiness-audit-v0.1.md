# 電子コミックprojection準備度監査 v0.1

更新日: 2026-10-02 JST

## 目的

隔離カテゴリDBの`ebook_comic`各商品について、最新スナップショットから非公開projection候補をメモリ内で組み立て、構造validatorへ適用する。出力はready件数とblocked件数だけに限定する。

商品ID、public ID、タイトル、URL、価格、review、entity値は出力しない。候補artifactも生成しない。
blockedが存在する場合はvalidatorの固定理由コード別件数だけを出力し、商品を特定できる値は出力しない。
review平均と件数の片方だけが存在する場合は、値を補完せず`PROJECTION_REVIEW_PAIR_INCOMPLETE`として集計する。

## 入力境界

既存カテゴリ収集健全性が`HEALTHY`である場合だけ、SQLite read-only modeで最新スナップショットを読む。source namespaceは`FANZA / ebook / comic / ebook_comic`へ固定する。

contributorの`author`と`manufacture`は別配列としてprojection validatorへ渡し、意味変換やカテゴリ横断統合を行わない。

## freshness境界

カテゴリ収集健全性が全sourceの最大許容経過時間内であることを確認した場合だけ、構造候補へ`CURRENT`を渡す。これは公式更新時刻、リアルタイム性、公開freshness表示を承認するものではない。

## 安全境界

監査結果は `READY_FOR_FIELD_AND_SEMANTICS_REVIEW` に留める。構造readyでも次はすべてfalseである。

- artifact生成
- DB書き込み
- contributor semantics確認
- field rights確認
- Compliance承認
- 公開・affiliate・Production

公式回答後も自動昇格せず、03 COMPLIANCEの判断とユーザー承認を必要とする。
