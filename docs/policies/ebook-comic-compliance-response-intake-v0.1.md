# 電子コミックCompliance回答取込 v0.1

更新日: 2026-10-02 JST

## 現在状態

ユーザーから、電子コミックCompliance確認票を2026-10-02 JSTに手動送信したとの報告を受領した。問い合わせID、アカウント情報、送信画面、メールアドレス等はリポジトリへ保存しない。現時点の状態は公式回答待ちである。

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
