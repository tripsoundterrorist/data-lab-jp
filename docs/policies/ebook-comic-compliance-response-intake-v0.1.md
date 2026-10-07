# 電子コミックCompliance回答取込 v0.1

更新日: 2026-10-07 JST

## 現在状態

ユーザーから、電子コミックCompliance確認票を2026-10-02 JSTに手動送信したとの報告を受領した。問い合わせID、アカウント情報、送信画面、メールアドレス等はリポジトリへ保存しない。

2026-10-05の公式回答を受領済みで、2026-10-06の追加回答により作者名・出版社名の
表示許可も確認した。取得項目・画像・保存条件の記録は
`../evidence/ebook-comic-official-response-sanitized-20261005.json`、追加回答は
`../evidence/books-followup-official-response-sanitized-20261007.json`を参照する。

現状は回答受領済み・別途COMPLIANCE再判定の候補であり、公開承認済みではない。
具体条件の対応、画像配信方式、API非表示・対象外になった後の保持等の残件は
`books-followup-official-response-assessment-20261007.md`で整理する。
通常利用の許可と詳細条件の残件を区別し、回答取込だけで公開・affiliate・Production
の権限を付与しない。

## 目的

公式回答を受領した際、原文や個人情報を直接処理せず、4つのquestion IDごとに明示された状態だけをfail-closedで分類する。

許可する状態は次の5種である。

- `RESOLVED_ALLOW`
- `RESOLVED_DENY`
- `RESOLVED_REQUIREMENTS`
- `UNRESOLVED`
- `CONTRADICTORY`

解決済みにできるのは、回答で明示的に扱われたquestion IDだけである。他項目からの推測、包括回答の拡張解釈、未回答項目の自動許可は禁止する。

## 証拠境界

入力はDMMアフィリエイトサポートの直接回答またはDMM公式文書に限定する。安全な内部referenceにはURL、ローカルパス、メールアドレス、API ID、affiliate ID、パスワード、secret、tokenを含めない。

部分回答は `PARTIAL_OFFICIAL_RESPONSE`、矛盾は `CONTRADICTORY_OFFICIAL_RESPONSE` とする。4項目すべてが明示的に解決しても、結果は `READY_FOR_SEPARATE_COMPLIANCE_DECISION` に留める。

## 安全境界

- 回答取込だけでCompliance承認を作らない。
- Publication Gate、公開、affiliate、Productionを変更しない。
- raw回答、問い合わせID、個人情報、秘密情報を保存しない。
- 回答後も03 COMPLIANCEの個別判断とユーザー承認を必要とする。
