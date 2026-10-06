# FANZA電子コミック公式回答評価 v0.1

更新日: 2026-10-06 JST

## 対象

2026-10-05 16:15 JSTに受領したDMMアフィリエイトサポート回答を、
`FANZA / ebook / comic / ebook_comic`だけへ適用する。外部転載禁止の注意に従い、
回答原文、担当者名、非公開問い合わせURLはリポジトリへ保存しない。

## 判定

- 商品情報API由来項目の表示・比較利用: 既存回答と同様の条件が適用されるため
  `RESOLVED_REQUIREMENTS`。
- 画像: サポートが指定した公式画像ルール上、FANZAブックスの商品メイン画像、
  サンプル画像（小・大）は利用可能と掲載される。拡大・縮小以外の加工を行わず、
  service固有制限に従う条件で`RESOLVED_REQUIREMENTS`。
- contributor semantics: `author`は作者名、`manufacture`は出版社名であることを確認。
  ただし質問後半の名称表示可否は回答で明示されていないため、この質問群全体は
  `UNRESOLVED`を維持する。
- sanitized raw、正規化価格履歴の保存・更新・削除: 既存回答と同様の条件が適用
  されるため`RESOLVED_REQUIREMENTS`。

画像根拠:

- `https://affiliate.dmm.com/guide/diagram/ad/use`
- `https://affiliate.dmm.com/guide/diagram/ad/restriction`

制限ページの許諾情報には「2024年9月時点」と表示されるが、今回のサポート回答が
当該ページを参照先として指定した事実を記録する。将来の変更可能性を考慮し、公開時
には再確認する。

## 境界

この回答をFANZA電子書籍BL、DMM.com写真集、同人、動画へ適用しない。現状態は
`PARTIAL_OFFICIAL_RESPONSE`であり、03 COMPLIANCEの別判定候補にも未到達である。
公開、affiliate有効化、sitemap、robots、DB、Collector、Production変更を許可しない。
