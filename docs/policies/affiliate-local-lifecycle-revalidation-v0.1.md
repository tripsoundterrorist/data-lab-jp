# Affiliate local lifecycle revalidation v0.1

## Purpose

Cloudflare WorkerからDMM ItemList APIへの上流接続失敗を受け、既存のローカル
Collector実行環境を使う単発・5件限定の代替transport候補である。新規サービス、
有料枠、X投稿、Publication Gate解除、公開ページ変更は行わない。

## Safety boundary

- 既定CLIはDRY_RUNで、DMM API呼出しもD1書込みも行わない。
- LIVEは`--execute --confirm LIVE_LOCAL_DMM_D1_REVALIDATION`の完全一致が必要。
- 対象は`CONDITIONALLY_APPROVED`かつ`RESOLVED`の古い順5件だけ。
- 公式APIのcontent ID完全一致と許可HTTPS hostを満たす場合だけ有効化する。
- 0件・不一致・affiliate URL欠落は無効化する。
- 通信失敗など未確認状態もfail-closedで無効化する。
- D1更新は1トランザクションの一時SQLに限定し、実行後は成功・失敗を問わず削除する。
- stdoutは集計値とallowlist済みreason codeのみ。ID、URL、credential、SQL、応答本文、例外詳細を出さない。
- 自動retry、自動repair、lock解除、無制限loopは行わない。

## Activation state

候補実装のみ。Windows Task Schedulerへの登録・変更は本変更に含まれない。
まずDRY_RUN、fixture test、1回の手動LIVE canary、本番件数確認を順に行い、別途明示承認後に
既存16:00 Collector、17:00 Backup、18:00 Stale Checkと重ならない時刻で登録する。
