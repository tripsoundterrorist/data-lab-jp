# BOOKS Compliance確認順序 v0.1

更新日: 2026-10-07 JST

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

以下は確認票作成時の項目一覧である。回答受領後の現在状態は末尾の
「2026-10-07 回答受領後の確認順」を優先し、回答済み項目を再質問しない。

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

## 2026-10-06 次回問い合わせ準備

次回パケットは、電子コミックのcontributor名称表示可否1問と、BL固有scopeの
4問だけに限定する。`scripts/books_next_compliance_followup_packet.py`は内部レビュー用の
非送信パケットを生成するだけであり、送信、承認、公開、affiliate、Productionを
許可しない。写真集の問い合わせは、このパケットへの回答評価後に別scopeで扱う。

## 2026-10-07 回答受領後の確認順

2026-10-05のcomic回答と2026-10-06の追加回答を受領済みである。
comicの作者・出版社名称表示は確認済み。BLについては、既存の取得項目の
表示・比較と保存・履歴条件の適用、および作者・出版社名称表示を確認した。
BLへの適用は追加回答による明示確認であり、comic回答からの推測ではない。
過去の回答・次回パケットの記載は履歴であり、同じ質問の再送指示ではない。

現在の確認順は次のとおりとする。

1. `books-followup-official-response-assessment-20261007.md`を基準に、通常利用の
   許可記録と詳細条件の残件を分離する。発売日・定価は両質問に含まれており、
   質問対象外として扱わない。ただし条件なしの許可を推測しない。
2. 許可画像・拡縮のみの条件を維持し、採用予定の画像配信方式、直リンク・
   クレジットの具体条件と、公開直前の公式画像ルール再確認を残件として扱う。
3. API非表示・対象外になった後の非公開DB履歴、ログ、バックアップ等の保持を、
   通常の履歴表示・保持・更新許可と区別する。「既存条件を適用」という回答から
   無期限保持や詳細条件の解決を推測しない。
4. 03 COMPLIANCEの別判定に必要な残件だけを整理し、問い合わせが必要か判断する。
   回答済みの作者・出版社名称表示やBLへの適用確認を同じscopeで再質問しない。
5. 写真集はDMM.comとFANZAのscopeを分離し、既存確認票を別途レビューする。
   BOOKS追加回答を写真集へ転用せず、DMM BOOKS画像禁止は明示的な更新回答まで維持する。

回答群の分類完了は、詳細条件の全解決、COMPLIANCE承認、公開承認を意味しない。
この整理は問い合わせ送信、収集処理、保持・削除設定、公開Gate、affiliate、
Productionを変更しない。10月10日以降の100商品MVP計測レビューをP0として優先する。
