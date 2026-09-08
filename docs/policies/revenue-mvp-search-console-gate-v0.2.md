# Revenue MVP Search Console Gate v0.3

`scripts/revenue_mvp_search_console_gate.py` はSearch Console送信前のread-only検査である。
公開固定ページ9件についてtitle、description、canonical、sitemap、robots、JSON-LDを確認し、
404と未公開商品ページがnoindexであることを必須とする。

合格は固定ページの送信準備完了だけを意味する。Search Consoleへの書込みは行わず、
Public Dataが公開許可されるまで商品一覧・商品詳細のインデックス申請は禁止する。

2026-09-05にoperatorがDomain property `datalabx.jp`へ完全URLのsitemapを登録し、
トップページのインデックス登録をリクエストしたことを記録する。

2026-09-08のread-only Search Console確認で、sitemapの最終読込日が
2026-09-08、statusが成功、検出ページ数が9であることを確認した。同日の
URL検査でトップページがGoogleに登録済みかつHTTPS配信であることを確認した。
再送信、index登録リクエスト、設定変更は行っていない。

この確認はトップページ以外の全URLがindex済みであることを意味しない。
商品一覧・商品詳細のindexingは引き続き禁止する。
