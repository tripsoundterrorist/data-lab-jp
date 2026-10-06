# BOOKS 次回問い合わせパケット v0.1

更新日: 2026-10-06 JST

## 目的

電子コミックの公式回答で残った1点と、FANZA電子書籍BL固有の4点を、
重複なく手動確認できる問い合わせ文へまとめる。

このパケットは送信準備専用である。問い合わせ送信、COMPLIANCE承認、
Publication Gate変更、affiliate有効化、Production変更を許可しない。

## 収録範囲

- `FANZA/ebook/comic/ebook_comic`: `author`と`manufacture`の名称表示可否のみ
- `FANZA/ebook/BL`: 取得項目、画像、contributor、保存・履歴の4問

電子コミックで回答済みの取得項目、画像、保存・履歴を再質問しない。
電子コミック回答をBLへ自動適用しない。写真集、同人、動画は対象外とする。

## 生成

```powershell
python scripts/books_next_compliance_followup_packet.py
```

出力は内部レビュー用JSONであり、自動送信しない。`send_authorized`、
`external_send_performed`、`compliance_approved`、`publication_allowed`、
`affiliate_allowed`、`production_write_allowed`はすべて`false`のままとする。

## 送信前の手動確認

1. 03 COMPLIANCEが質問とscopeを確認する。
2. 前回回答と重複していないことを確認する。
3. アカウント情報、問い合わせURL、秘密値が含まれないことを確認する。
4. ユーザーが送信時点で明示承認する。

送信後も、回答のsanitized intakeとscope別判定が完了するまで、BLの公開、
affiliate導線、sitemap、robots、Productionへの反映を行わない。

## 2026-10-06 送信状況

ユーザーによる手動送信完了の申告を、本文、アカウント情報、問い合わせURLを含めず
sanitized evidenceへ記録した。状態は`SUBMITTED_AWAITING_OFFICIAL_RESPONSE`であり、
回答受領と03 COMPLIANCE評価までは全release gateを閉じたままとする。
