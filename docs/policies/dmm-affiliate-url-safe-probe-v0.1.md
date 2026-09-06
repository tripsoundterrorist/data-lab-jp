# DATA LAB DMM Affiliate URL Safe Probe v0.1

## Purpose

`scripts/probe-dmm-affiliate-url.py` は、DMM Web APIの商品1件応答に
`affiliateURL` が存在し、安全なURL形状であるかをread-onlyで確認する。

API requestは最大1回、`hits=1`、`offset=1` に固定する。
DB、ファイル、API応答、URLを保存せず、本番・Cloudflare・Publication Gateを変更しない。

## Safe output

出力は次の安全な要約だけに限定する。

- HTTP/API成功の真偽
- 応答件数（0または1）
- affiliate linkの存在
- HTTPS
- DMM/FANZA系host
- embedded credentialなし
- 2,048文字以内
- response非保存
- DB writeなし
- 固定reason code

API ID、affiliate ID、request URL、affiliate URL、通常URL、title、content ID、
product ID、response本文、例外文は出力しない。

## Validation order

1. `.env` に `DMM_API_ID` と `DMM_AFFILIATE_ID` が存在することを確認
2. dry-runでは外部requestを行わず終了
3. liveではItemListへ1回だけrequest
4. HTTP成功とAPI status 200を確認
5. itemが一件だけであることを確認
6. `affiliateURL` の安全な形状だけを判定

欠落や不正形式からaffiliate eligibility、availability、purchasabilityを推測しない。

## Windows commands

まず外部通信なしで環境だけを確認する。

```powershell
python .\scripts\probe-dmm-affiliate-url.py --dry-run
```

dry-run成功後、ユーザー承認を経て一件だけ実API確認する。

```powershell
python .\scripts\probe-dmm-affiliate-url.py
```

このprobeのPASSはAPI応答形状の確認だけを意味し、Issue #66、Release Gate、
affiliate runtime接続、本番CTAを解除しない。

## Legacy note

`scripts/check-dmm-api.ps1` は調査用に商品情報や通常URLを表示する。
affiliate runtime確認では出力最小化された本probeを優先する。


## v0.1 diagnostic extension

When an affiliate URL is present, the probe may report only bounded booleans for
fixed host families: `dmm.co.jp`, `dmm.com`, `fanza.com`, and
`fanza.co.jp`, plus an unclassified flag. It never emits the hostname or URL.

The diagnostic classification alone does not expand `ALLOWED_HOST_SUFFIXES`.
After a bounded live probe confirmed that the official DMM ItemList API returns
an HTTPS affiliate link in the `fanza.co.jp` family, that family was added to
the technical URL-shape allowlist. This does not unlock Issue #66, publication,
affiliate integration, or production deployment gates.
