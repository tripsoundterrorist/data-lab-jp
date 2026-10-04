# FANZA電子書籍BL Compliance response intake v0.1

更新日: 2026-10-05 JST

`scripts/ebook_bl_compliance_response_intake.py`は、FANZA電子書籍BLについての
sanitized公式回答を、BL固有の4質問へ厳密に対応付けるfail-closed intakeである。

電子コミック向け回答をBLへ推定適用しない。回答日時、公式source種別、安全な
参照名、全質問の状態、明示的に回答された質問IDを要求する。未回答、矛盾、未知の
質問、推定による解決、URL・メール・秘密値を含む参照は遮断する。

全質問が明示的に解決しても、結果は03 COMPLIANCEの別判定候補に限られる。
COMPLIANCE承認、Publication Gate変更、公開、affiliate、外部送信、DBまたは
Production書き込みは許可しない。
