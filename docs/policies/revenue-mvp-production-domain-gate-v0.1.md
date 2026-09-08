# Revenue MVP Production Domain Gate v0.1

DMMアフィリエイトサポート回答に基づき、API利用は承認済みサイトに限定し、
URL変更時は申請を必要とする。確認ではURL、affiliate ID、アカウント情報を
入力・保存せず、次のboolean証跡だけをoperatorが確認する。

- 承認済みサイトが確認できた
- production domainが承認済みサイトと一致する
- URL変更申請がpendingではない

全条件が揃っても`READY_FOR_CONDITION_REVIEW`に留まり、Gate、production変更、
route、affiliate row、deploymentを自動で有効化しない。現在値は未確認として
fail-closedを維持する。
