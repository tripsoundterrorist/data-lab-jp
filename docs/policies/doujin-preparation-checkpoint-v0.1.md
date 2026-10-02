# 同人カテゴリ準備チェックポイント v0.1

更新日: 2026-10-02 JST

## 目的

同人カテゴリのcollection-only準備を安全な区切りで停止し、公開中100商品Revenue MVPの正式計測レビューへ戻れる状態を明示する。

チェックポイントは次の既存監査を読み取り専用で統合する。

- entity参照の整合性
- 公開projection構造の準備度
- field rightsの確認範囲
- 最新価格スナップショットの算術整合性
- DMMへ手動確認すべき未解決項目

商品情報、entity値、価格値、URL、rawレスポンスは出力しない。DB、リポジトリ、外部サービスへの書き込みは行わない。

## P0復帰境界

- GA4正式評価期間: 2026-10-02〜2026-10-08 JST
- 初回正式レビュー: 2026-10-10 JST以降
- 10月10日の復帰は時刻による強制中断ではなく、このチェックポイントのような原子的作業単位を完了してから行う。
- スクリプトは自動実行、予約、通知、Production変更を行わない。

## 未解決の公式確認

最小の手動問い合わせ候補は次の5項目である。

1. `DOUJIN_SOURCE_SCOPE_APPLICABILITY`
2. `RELEASE_DATE_PUBLIC_DISPLAY`
3. `SANITIZED_RAW_RETENTION_ALLOWED`
4. `SANITIZED_RAW_RETENTION_DURATION`
5. `HISTORICAL_NORMALIZED_PRICE_RETENTION`

問い合わせ文面の準備完了は送信承認ではない。外部送信は別の明示的承認を必要とする。

## 維持する閉鎖状態

- Compliance承認: false
- 公開許可: false
- Production書き込み: false
- Publication Gate変更: false
- affiliate有効化: false
- sitemap追加・index許可: false

チェックポイントが `READY_TO_PAUSE_FOR_P0_REVIEW` でも、これはカテゴリ公開準備の技術的区切りだけを表し、同人カテゴリの公開可否を表さない。
