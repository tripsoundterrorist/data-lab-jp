# Revenue MVP Official Answer Matrix v0.2

2026-09-08に、運営者が受領したDMMアフィリエイトサポート回答の
sanitize済み判断を12 topicへ記録した。raw email、送信者、メールアドレス、
アカウント情報、affiliate ID、URL、画像ファイルは保存しない。

APIデータの履歴表示、保持・更新、独自集計は`ALLOWED`とする。画像利用、
販売・掲載終了時の取下げ、公式ランキングとの誤認防止、PR表示、承認済み
サイトURL、SNS導線・登録・画像・自動投稿は`CONDITIONALLY_ALLOWED`とする。

2026-09-14に運営者がX追加サイト承認を確認したため、
`SNS_ACCOUNT_REGISTRATION`だけを条件確認済みとして記録した。アカウント名、
affiliate ID、メール、URL、回答本文は保存しない。

残る`SNS_TO_SITE_TO_FANZA_FUNNEL`、`SNS_PRODUCT_MEDIA_USE`、
`AUTOMATED_FACT_POSTING`は問い合わせ回答待ちでblockingを維持する。
X承認だけではSNS operation candidate、Publication Gate、affiliate enablement、
route、deployment、自動投稿、商品媒体利用を解除しない。Web Revenue MVPの
公式Lifecycle/Sort回答待ちとも独立した条件として扱う。
