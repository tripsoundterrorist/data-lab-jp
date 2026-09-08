# Revenue MVP Official Response Conditions v0.1

公式回答の条件付きtopicのうち、既存のfail-closed契約で証跡を確認できる
4件だけをverifiedとする。

- `API_IMAGE_USE`: API由来の商品メイン画像だけを候補とし、商品説明文、
  レビュー本文、人物画像、動画等は公開禁止とする。
- `DISCONTINUED_ITEM_HANDLING`: 明示的にunavailableと検証された商品は
  publication eligibleにならない。API zero-resultだけから終了を推定しない。
- `OFFICIAL_RANKING_CONFUSION`: DATA LAB独自集計でありDMM/FANZA公式の
  評価・順位ではないこと、算出対象・基準時刻・出典・制約を表示する。
- `PR_AD_AFFILIATE_DISCLOSURE`: CTAと同時に、視認可能な`PR`表記、
  affiliate linkであること、報酬関係を表示する。

SNS導線・SNS登録・SNS画像・自動投稿、およびproduction domainの承認確認は
未verifiedでありblockingを維持する。4件の証跡確認はpublic data、affiliate
row、route、deployment、SNS投稿、Publication Gateを有効化しない。
