# BOOKS category intake adapter v0.1

更新日: 2026-10-05 JST

`scripts/books_compliance_category_intake_adapter.py`は、sanitized公式回答を
scope routerで検証した後、明示された1カテゴリの既存response intakeへだけ渡す。

電子コミック、FANZA電子書籍BL、DMM.com写真集をexact
`site/service/floor/content_type`で分離する。回答に明記されていないカテゴリは
`TARGET_SCOPE_NOT_EXPLICIT`で遮断する。明示されていない質問群は推定せず、対象
カテゴリintakeへ`UNRESOLVED`として渡す。矛盾は解消せず、そのカテゴリ固有intakeの
矛盾状態を維持する。

このアダプターは回答原文、商品データ、URL、画像、秘密情報を扱わない。結果が
完全でも03 COMPLIANCEの別判定候補に限られ、COMPLIANCE承認、問い合わせ送信、
Publication Gate変更、公開、affiliate、sitemap、robots、DBまたはProduction
書き込みは許可しない。
