# Revenue MVP Local Preview Bundle v0.1

`scripts/revenue_mvp_local_preview.py`は、検証済みPublic Data候補と公開シェルをOS一時領域の新規ディレクトリへ統合し、ローカル確認用bundleを生成する。

## Safety boundary

- 入力candidateはOS temp root配下に限定し、既存のartifact validatorを通す。
- `publication_status=local_validation_only`かつ未解決の`rights_review_required`がある候補だけを受け付ける。
- 出力先はOS temp root配下の未作成ディレクトリに限定する。
- `robots.txt`は`Disallow: /`へ置き換える。
- ブラウザー側はlocalhost、127.0.0.1、::1でのみ未公開candidateを表示し、「ローカルプレビュー（非公開）」と明示する。
- Cloudflare、Git、production bundle、入力DB、Issue #66を変更しない。
- `publication_allowed=false`、`production_write_performed=false`を常に維持する。

ローカルプレビュー成功は公開承認ではない。商品データの本番配備、検索登録、アフィリエイト導線、SNS投稿は公式回答と別の明示承認が揃うまで禁止する。
