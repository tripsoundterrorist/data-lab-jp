# Revenue MVP Official Follow-up Packet v0.1

`scripts/revenue_mvp_official_followup_packet.py` は、Revenue MVPに残る
LifecycleとSort Semanticsの公式確認事項を、DMMアフィリエイトサポートへ
送付できる日本語の質問へまとめるpure/read-only contractである。

質問IDは `official_response_intake.py` のLifecycle 9項目とSort 8項目を
省略せず保持する。対外文面では関連する事項を5問と4問にまとめるが、回答の
取込み時は各question IDへ明示的に対応付ける。回答不能、個別判断、曖昧な回答を
推測で `RESOLVED` にしない。

このpacketはメール送信、問い合わせフォーム操作、APIアクセス、Gate変更、
publication、affiliate接続を行わない。`send_authorized=false`、
`gate_unlock_allowed=false`を固定し、送信はoperator action、回答はsanitize済み
Official Response Intakeと別reviewを必須とする。
