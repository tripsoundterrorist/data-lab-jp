# Revenue MVP Official Answer Matrix v0.1

Issue #66の12論点を、`ALLOWED`（許可）、`CONDITIONALLY_ALLOWED`（条件付き許可）、
`UNKNOWN`（不明）、`FOLLOW_UP_REQUIRED`（要追加確認）に分類するpure/read-only Gateである。

条件付き許可は、対応する実装条件の確認証跡がある場合だけreview candidateに含める。
不明、要追加確認、条件未確認、欠落、未知topicはfail-closedとする。Revenue MVP coreと
SNS運用は別々に判定し、SNS回答待ちだけでcore準備を止めない。

結果が`REVIEW_CANDIDATE`でも`gate_unlock_allowed=false`を維持する。公式回答の原文、
担当者情報、メールアドレス、認証情報は入力・保存せず、既存のOfficial Response Intake、
Blocker Registry、Publication Gateを別commit・別承認なしに変更しない。
