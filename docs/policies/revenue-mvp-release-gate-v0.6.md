# Revenue MVP Release Gate v0.6

`scripts/revenue_mvp_release_gate.py` は、静的shell、Public Data候補、
Search Console、本番スモーク、公式回答、Publication Gate、X導線を
一つのread-only結果へ集約する。ビルド、配備、公開状態変更、URL出力は行わない。

v0.6では、Revenue MVPの完了条件へアフィリエイト実配線を明示的に追加した。
APIへ `affiliate_id` を渡して収集した場合でも、DBの `item_url` は通常の商品ページURLであり、
アフィリエイトURLの実配線完了とはみなさない。

現時点では、API発行アフィリエイトURLを安全なWeb UI handoffへ供給する
production runtime providerが未接続である。このため
`affiliate_integration_allowed=false`、
`AFFILIATE_RUNTIME_NOT_CONNECTED`、
`IMPLEMENT_AFFILIATE_RUNTIME_PROVIDER` を返し、他の条件が揃っても
`READY_FOR_RELEASE_APPROVAL` へ進めない。

将来の接続時も、既存のAffiliate Link Policy、Adapter、UI Handoffに従い、
公式回答、lifecycle、URL検証、Publication Gate、CTA直近のPR表示をすべて満たす必要がある。
Public JSONや静的artifactへアフィリエイトURLを混入させることで解除してはならない。

全条件が揃った場合も `production_release_allowed` は常にfalseであり、
本番反映には別の明示承認が必要となる。
