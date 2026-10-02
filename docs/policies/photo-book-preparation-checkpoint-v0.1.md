# 写真集準備完了チェックポイント v0.1

更新日: 2026-10-02 JST

## 目的

公式確認待ちへ移る前に、写真集のsource境界とdeterministic public IDを匿名・読み取り専用で監査し、画像を含まない非公開projectionを架空データだけでリハーサルする。

## 実データ監査

隔離カテゴリDBの`photo_book`について、次の集計件数だけを出力する。

- 固定source namespace `DMM.com / ebook / photo / photo_book` の適合件数
- 商品URLが現在観測中の`book.dmm.com`境界に適合する件数
- release dateが妥当なdatetime形式である件数
- deterministic public IDの一意件数と衝突件数

商品ID、タイトル、URL全文、価格、review、entity、生成public IDは出力しない。

Rights Decision Matrixの既存禁止判断に従い、実データ監査のSELECT対象へ`image_json`を含めない。画像の取得可否やホストを公開権利の根拠にしない。

## 架空データ・リハーサル

完全review組、review両方欠損、genreあり、genreなしを架空データで確認する。想定外の商品ホストと、allowlistに存在しない画像フィールドがfail-closedで遮断されることも確認する。

実商品、画像、publication artifact、affiliate URL、外部通信は使用しない。

## 完了境界

全実データ境界、public ID一意性、全架空シナリオ、禁止入力遮断が成立した場合だけ`READY_FOR_OFFICIAL_RESPONSE`とする。

この状態は次を許可しない。

- DB・sanitized raw・履歴変更
- 実データprojection artifact生成
- contributor semantics・field rights・Compliance承認
- 公開・affiliate・sitemap
- Production書き込み

写真集は電子コミックの現在の問い合わせ回答を確認後、重複を除いた別問い合わせをユーザーが手動送信する。公式回答、03 COMPLIANCE判断、ユーザー承認まで、このチェックポイントで待機する。
