# BOOKS Compliance scope router v0.1

更新日: 2026-10-05 JST

`scripts/books_compliance_scope_router.py`は、公式回答の対象範囲を電子コミック、
FANZA電子書籍BL、DMM.com写真集へ誤って横展開しないための純粋な
fail-closed判定器である。

回答原文は入力・保存せず、回答日時、公式source種別、安全な参照名、回答で
明示されたexact `site/service/floor/content_type`、明示的に回答された質問群だけを
sanitized入力として受け取る。URL、メールアドレス、秘密値を含む参照名は拒否する。

対象scopeは次の3件へ固定する。

- `FANZA / ebook / comic / ebook_comic`
- `FANZA / ebook / bl / ebook_bl`
- `DMM.com / ebook / photo / photo_book`

電子コミックだけが明記された回答をBLまたは写真集へ適用しない。4質問群
（取得項目、画像、contributor、保存・履歴）がすべて明示されても、scopeが欠ける
場合は`PARTIAL_EXPLICIT_SCOPE`を返す。全scopeと全質問群が明示された場合も、
到達状態は各category固有intakeへ渡せることだけを示す。

この判定はCOMPLIANCE承認、問い合わせ送信、公開、affiliate、sitemap、robots、
Production、DB書き込みを許可しない。各categoryの既存intake、03 COMPLIANCE判断、
ユーザーのaction-time承認は省略できない。
