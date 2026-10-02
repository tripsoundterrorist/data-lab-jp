# FANZA BL電子書籍構造監査 v0.1

更新日: 2026-10-02 JST

## 目的

`ebook_bl`の既存collection-onlyデータを読み取り専用で匿名監査し、BLフロア固有のprojection設計へ進める構造か確認する。

電子コミックと同じ`ebook`サービスであっても、field rights、entity semantics、公開条件、affiliate条件を自動的に同一視しない。

## 監査対象

- 固定source namespace `FANZA / ebook / bl / ebook_bl`
- タイトル、発売日、HTTPS商品URL、HTTPS画像
- series、genre
- 現在価格、定価、割引、reviewの存在
- contributor役割キーと構造完全性

出力は項目別件数と役割キー別集計だけに限定する。商品ID、タイトル、URL、価格、review、entity値、rawレスポンスは出力しない。

## 安全境界

- 隔離DBをSQLite read-only modeで開く。
- API取得、DB更新、artifact生成、公開projection生成を行わない。
- API上の役割キーをentityの意味確定として扱わない。
- 画像の存在を表示権の根拠にしない。
- Production、Publication Gate、affiliate、sitemap、robotsを変更しない。
- 公開中の100商品Revenue MVPと正式計測をP0として維持する。

監査成功は`READY_FOR_EBOOK_BL_STRUCTURE_REVIEW`を意味するだけで、BL電子書籍の公開・収益化・Compliance適合を承認しない。

