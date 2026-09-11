# DATA LAB Affiliate Pages Secret State v0.1

## Purpose

Cloudflare Pages production環境のsecretを値ではなくbinding名だけで確認し、
affiliate deployment preflightへ安全に渡す。

2026-09-11のread-only確認では、`data-lab-jp` production環境のsecretは0件だった。
このため`DMM_API_ID`と`DMM_AFFILIATE_ID`は未設定としてBLOCKEDを維持する。

## Secret boundary

- secret値を入力、取得、表示、保存しない
- command引数、Git、ログ、Issue、PRへsecret値を載せない
- 未知名、重複名、未確認状態をreadyにしない
- 必要な2つのbinding名が完全一致した場合だけ、名前をpreflightへ渡す
- Gate自体はsecret登録、deploy、route有効化、課金変更を許可しない

## Future registration

登録が承認された場合は、値をコマンドライン引数へ含めず、Wranglerの対話入力または
Cloudflare dashboardの暗号化secret入力を使用する。登録後は`pages secret list`で名前だけを
再確認する。値をチャットへ貼り付けない。

Free planの変更や課金が必要と表示された場合は、その場で停止してoperatorへ通知する。
