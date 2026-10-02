# 電子コミックreview組ポリシー候補 v0.1

更新日: 2026-10-02 JST

## 目的

電子コミック収集データでは、review平均とreview件数が独立したnullable項目として保存される。片方だけが取得された観測を、0や未評価と推測して補完しないための非公開projection設計候補を定義する。

## 候補規則

- 平均と件数が両方有効: 完全な組として保持候補
- 両方が欠損: review表示を省略する候補
- 片方だけが有効: 元の履歴を変更せず、review表示全体を省略する候補
- 負数、非有限値、bool等の不正値: fail-closed

省略は値の削除、0埋め、意味変換ではない。収集DBとsanitized rawの履歴を変更せず、将来の表示用projectionでreview項目を出さない候補に限る。

## 安全境界

この候補は純粋判定器であり、カテゴリDB、publication artifact、既存100商品MVPへ接続しない。次はすべてfalseのままとする。

- 履歴データ変更
- 推測値生成
- Compliance承認
- 公開・affiliate・sitemap
- Production書き込み

公式回答で電子コミックのreview表示範囲を確認後、03 COMPLIANCEの判断とユーザー承認を得るまで接続しない。
