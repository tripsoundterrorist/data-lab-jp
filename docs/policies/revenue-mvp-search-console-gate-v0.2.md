# Revenue MVP Search Console Gate v0.2

`scripts/revenue_mvp_search_console_gate.py` はSearch Console送信前のread-only検査である。
公開固定ページ9件についてtitle、description、canonical、sitemap、robots、JSON-LDを確認し、
404と未公開商品ページがnoindexであることを必須とする。

合格は固定ページの送信準備完了だけを意味する。Search Consoleへの書込みは行わず、
Public Dataが公開許可されるまで商品一覧・商品詳細のインデックス申請は禁止する。

2026-09-05にoperatorがDomain property `datalabx.jp`へ完全URLのsitemapを登録し、
トップページのインデックス登録をリクエストしたことを記録する。これは操作完了の証跡であり、
Googleによるsitemap処理成功やトップページのインデックス登録完了を意味しない。
確認できるまでは両者をfalseとし、再送せず状態を監視する。
