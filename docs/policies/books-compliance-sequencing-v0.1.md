# BOOKS Compliance確認順序 v0.1

更新日: 2026-10-04 JST

## 目的

電子コミック、FANZA電子書籍BL、写真集の確認票に共通する質問を整理し、
進行中の公式問い合わせへの回答を確認した後、不要な重複問い合わせを
送らないための手順を定める。

この文書は内部の非送信手順である。公式問い合わせ、COMPLIANCE承認、
Publication Gate変更、affiliate有効化、Production変更を許可しない。

## 処理順

1. 現在進行中の公式問い合わせへの回答を受領する。
2. 03 COMPLIANCEが回答原文、対象service/floor、取得日時を確認する。
3. 回答を次の共通4群へ対応付ける。
   - 商品情報API取得項目の表示・比較利用範囲
   - 商品メイン画像の表示・加工・リンク・クレジット条件
   - contributor roleの公式な意味と名称表示可否
   - sanitized raw、正規化データ、価格履歴の保存・更新・削除条件
4. 回答が明示的に対象とするservice/floorだけを回答済みとする。
5. 電子コミック確認票から回答済みの質問を除外し、残件だけを手動レビューする。
6. 電子コミックの確認完了後、BL、写真集の順に、共通回答を自動適用せず
   category固有の残件を確定する。
7. 送信する場合は、03 COMPLIANCE確認とユーザーのaction-time承認を別々に得る。

## 共通質問群

### A. 取得項目の利用範囲

タイトル、商品URL、series、genre、現在価格、review、発売日、定価について、
対象service/floorで表示・比較へ利用できるかを確認する。

### B. 画像

APIの商品メイン画像について、表示可否、対象サイズ、加工、直リンク、
クレジット等の条件を確認する。あるcategoryへの回答を別categoryへ適用しない。

### C. contributor semantics

`author`、`manufacture`、必要な場合は`actor`または`actress`の公式な意味と、
取得名称をページへ表示できるかを確認する。

### D. 保存と履歴

sanitized raw、正規化データ、価格履歴について、保存期間、更新、削除条件を
確認する。回答がない場合はcollection-onlyかつ非公開を維持する。

## category固有の残件

- 電子コミック: `review.average`と`review.count`の組としての表示、
  `author`と`manufacture`の意味、FANZA電子コミック画像の範囲。
- FANZA電子書籍BL: comic floorと同一scopeであると仮定しない。
  BL floor固有の画像範囲とfield rightsを確認する。
- 写真集: DMM.com `ebook/photo`とFANZA `ebook/photo`を分離する。
  既存のDMM Books画像禁止を明示的な更新回答まで維持し、
  `actor`、`actress`、`author`、`manufacture`をsourceごとに確認する。

## fail-closed判定

次のいずれかが欠ける場合、対象categoryの公開準備を進めない。

- 回答原文
- 回答日時
- 対象service/floor
- 質問と回答の対応
- 03 COMPLIANCEの明示判断
- 公開操作に対するユーザーの個別承認

`READY_FOR_MANUAL_COMPLIANCE_REVIEW`、`READY_FOR_OFFICIAL_RESPONSE`、
または技術テスト成功は、送信、公開、affiliate、sitemap、robots、Productionの
許可を意味しない。

## 2026-10-05 電子コミック回答の反映

電子コミックへの公式回答は、`ebook_comic`のexact scopeだけへsanitized intakeした。
取得項目、画像、保存・履歴は条件付き解決、contributorは意味だけ確認済みで名称表示
可否が未解決のため、全体状態は`PARTIAL_OFFICIAL_RESPONSE`である。

この回答をBLまたは写真集へ自動適用しない。次の問い合わせは、電子コミックの
contributor表示可否と、BL固有scopeを重複なく確認する順序を維持する。
