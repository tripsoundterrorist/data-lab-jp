# DATA LAB Affiliate Pages Secret State v0.2

## Change from v0.1

2026-09-11にoperator承認後、ローカルのGit除外済みsecret sourceから値を表示せず、
Wrangler標準入力でCloudflare Pages production環境へ次の2 bindingを登録した。

- `DMM_API_ID`
- `DMM_AFFILIATE_ID`

登録後のread-only確認では、必要2件がいずれもencrypted secretとして存在した。
値はcommand引数、標準出力、Git、Issue、PR、チャットへ出していない。

## Boundary

この証跡はbinding名の存在だけを確認する。値の正当性、API疎通、affiliate URL生成、
route配備、runtime接続、affiliate有効化、公開、課金変更を証明・許可しない。

secret登録による新規deploymentは発生せず、確認時点の最新production deployment sourceは
登録前と同一だった。次回deployment時にsecretが利用可能になるため、route配備は引き続き
別承認とする。
