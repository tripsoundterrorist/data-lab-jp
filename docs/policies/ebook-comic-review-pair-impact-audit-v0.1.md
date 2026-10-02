# 電子コミックreview組影響監査 v0.1

更新日: 2026-10-02 JST

## 目的

隔離カテゴリDBの`ebook_comic`最新スナップショットへ、未接続のreview組ポリシー候補を読み取り専用で適用し、完全・欠損・片側欠損・不正の件数だけを確認する。

## 出力境界

出力は次の集計値に限定する。

- 対象商品数
- 完全なreview組の件数
- 両方欠損の件数
- 片側欠損の件数
- 不正値の件数
- 将来projectionでの省略候補件数

商品ID、タイトル、URL、review値、public IDは出力しない。artifactも生成しない。

## 安全境界

監査はSQLite read-only modeで実行し、収集DB、sanitized raw、履歴、既存100商品MVPを変更しない。省略候補は公開projectionへの接続許可ではない。

不正値が1件でもあればfail-closedとする。不正値がなくても、次はすべてfalseのままである。

- DB・履歴変更
- 推測値生成
- Compliance承認
- publication artifact生成
- 公開・affiliate・sitemap
- Production書き込み

公式回答、03 COMPLIANCE判断、ユーザー承認を得るまで、review組ポリシー候補をprojectionへ接続しない。
