# Revenue MVP Search Console Gate v0.1

`scripts/revenue_mvp_search_console_gate.py` はSearch Console送信前のread-only検査である。
公開固定ページ9件についてtitle、description、canonical、sitemap、robots、JSON-LDを確認し、
404と未公開商品ページがnoindexであることを必須とする。

合格は固定ページの送信準備完了だけを意味する。Search Consoleへの書込みは行わず、
Public Dataが公開許可されるまで商品一覧・商品詳細のインデックス申請は禁止する。
