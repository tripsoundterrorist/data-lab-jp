# 写真集Compliance回答取込 v0.1

更新日: 2026-10-07 JST

## 現在状態

写真集Compliance確認票は準備済みだが未送信である。2026年10月6日のBOOKS追加回答は
受領・確認済みであり、写真集scopeへの許可は含まれない。
`books-followup-official-response-assessment-20261007.md`に回答と残件を整理している。

2026年10月7日、ユーザーから電子コミック・BLのAPI非表示・対象外になった後の
保持・削除・価格履歴公開に関する追加問い合わせを手動送信したとの報告を受領した。
現在はその回答待ちであり、回答後に写真集確認票の重複を整理し、別scopeの問い合わせを
手動レビューする。写真集問い合わせを送信済みとは扱わず、回答も推測適用しない。

問い合わせID、アカウント情報、送信画面、メールアドレス等はリポジトリへ保存しない。

## 目的

将来写真集への公式回答を受領した場合、回答本文や個人情報を直接保存せず、4つのquestion IDごとに明示された状態だけをfail-closedで分類する。

許可する状態は次の5種だけである。

- `RESOLVED_ALLOW`
- `RESOLVED_DENY`
- `RESOLVED_REQUIREMENTS`
- `UNRESOLVED`
- `CONTRADICTORY`

解決済みにできるのは、回答で明示的に扱われたquestion IDだけである。他項目からの推論、包括回答の拡張解釈、無回答項目の自動解決は禁止する。

## 証拠境界

入力はDMMアフィリエイトサポートの直接回答またはDMM公式文書に限定する。安全な内部referenceにはURL、ローカルパス、メールアドレス、API ID、affiliate ID、パスワード、secret、tokenを含めない。

部分回答は`PARTIAL_OFFICIAL_RESPONSE`、矛盾は`CONTRADICTORY_OFFICIAL_RESPONSE`とする。4項目がすべて明示的に解決しても、結果は`READY_FOR_SEPARATE_COMPLIANCE_DECISION`に留める。

DMM Books商品画像の既存禁止判断は、回答取込だけでは変更しない。画像に関する回答を03 COMPLIANCEで個別に対応付けて判断する。

## 安全境界

- 回答取込だけでCompliance承認しない。
- Publication Gate、公開、affiliate、Productionを変更しない。
- raw回答、問い合わせID、個人情報、秘密情報を保存しない。
- 回答後に03 COMPLIANCEの個別判断とユーザー承認を必要とする。
