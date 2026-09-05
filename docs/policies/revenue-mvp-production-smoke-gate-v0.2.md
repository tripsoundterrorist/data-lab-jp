# Revenue MVP Production Smoke Gate v0.2

`scripts/revenue_mvp_production_smoke_gate.py` は、`https://datalabx.jp` の固定URLだけを
GETするread-only本番確認である。書込み、配備、Search Console操作、API認証は行わない。

固定公開9ページのHTTP 200とcanonical、robots、sitemap、カスタム404を検査する。
未公開の商品一覧・商品詳細はHTTP 200でも`noindex`が必須であり、このGateが合格しても
商品データ公開または商品ページのインデックスを許可しない。

タイムアウト、通信失敗、応答欠損、正式ドメインからの逸脱は`FAIL_CLOSED`とする。
通信失敗はホーム、分析コラム、情報/規約、非公開商品route、SEO asset、404 routeの
安全な区分、失敗URL数、区分数だけを返す。
URL、本文、例外、redirect先、credentialは失敗結果へ出力しない。実行結果は観測時点の
スモーク証跡であり、継続的な可用性保証ではない。
