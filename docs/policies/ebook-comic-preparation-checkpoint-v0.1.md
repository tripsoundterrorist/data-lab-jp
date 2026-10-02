# 電子コミック準備完了チェックポイント v0.1

更新日: 2026-10-02 JST

## 目的

公式回答待ちへ移る前に、電子コミックのsource境界を匿名・読み取り専用で監査し、review組の安全な省略候補を架空データだけで非公開リハーサルする。

## 実データ監査

隔離カテゴリDBの`ebook_comic`について、次の件数だけを出力する。

- 固定source namespace適合件数
- 商品URLが現在観測中の`book.dmm.co.jp`境界に適合する件数
- 画像URLが現在観測中の`ebook-assets.dmm.co.jp`境界に適合する件数
- release dateが妥当なdatetime形式である件数
- deterministic public IDの一意件数と衝突件数

ホスト境界は現在のAPI観測構造を固定する技術境界であり、画像表示権、公開許可、affiliate利用許可を意味しない。

商品ID、タイトル、URL全文、画像URL全文、価格、review値、生成public IDは出力しない。

## 架空データ・リハーサル

完全review組、両方欠損、片側欠損の3シナリオを使用する。片側欠損は収集履歴を変更せず、表示projection上だけ両方を省略する候補としてvalidatorへ渡す。

想定外ホストは遮断されることも確認する。実商品、publication artifact、affiliate URL、外部通信は使用しない。

## 完了境界

全実データ境界、public ID一意性、全架空シナリオ、禁止入力遮断が成立した場合だけ`READY_FOR_OFFICIAL_RESPONSE`とする。

この状態は次を許可しない。

- DB・sanitized raw・履歴変更
- 実データprojection artifact生成
- Compliance承認
- 公開・affiliate・sitemap
- Production書き込み

公式回答、03 COMPLIANCE判断、ユーザー承認まで電子コミックはこのチェックポイントで待機する。
