# 電子コミック構造監査 v0.1

更新日: 2026-10-02 JST

## 目的

`ebook_comic`の既存collection-onlyデータを読み取り専用で監査し、同人向けのentity構造を誤って流用せずに、電子コミック固有のprojection設計へ進めるか判断する。

出力は項目別件数とcontributorの役割キー別集計だけに限定する。人物名、出版社名、商品ID、タイトル、URL、価格値、rawレスポンスは出力しない。

## 監査対象

- タイトル
- 発売日
- HTTPS商品URL
- HTTPS画像
- series
- genre
- 現在価格、定価、割引、reviewの存在
- contributor JSONに出現する役割キーと構造完全性

役割キーはAPIレスポンス上の構造ラベルとして扱うだけであり、author、maker、publisher、brand等の意味やカテゴリ横断の同一性を確定しない。

## 安全境界

- 隔離DBをSQLite read-only modeで開く。
- API取得、DB更新、成果物生成、公開projection生成を行わない。
- entity semanticsとfield rightsは未確認のまま維持する。
- Production、Publication Gate、affiliate、sitemap、robotsを変更しない。
- 100商品Revenue MVPのP0レビューを遅延させない。

監査成功は `READY_FOR_EBOOK_COMIC_STRUCTURE_REVIEW` を意味するだけで、電子コミックの公開・収益化・規約適合を承認しない。
