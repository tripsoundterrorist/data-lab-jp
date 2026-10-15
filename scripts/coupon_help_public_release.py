"""Public artifact transform. Local code readiness is not deployment approval."""
from scripts.coupon_help_candidate_bundle import build_candidate_bundle, _replace_once


def build_public_release(sources: dict[str, bytes]) -> dict[str, bytes]:
    bundle = build_candidate_bundle(sources)
    article = bundle['coupon-help.html'].decode('utf-8')
    for old, new in (
        ('  <meta name="robots" content="noindex, nofollow">\n', ''),
        ('    <p class="status">未公開の下書きです。公開審査・公開承認は未完了です。</p>\n', ''),
        ('DATA LAB</strong> / ローカル確認用', 'DATA LAB</strong>'),
        ('公開候補のローカル確認用。公開承認は未完了です。', ''),
    ):
        article = _replace_once(article, old, new)
    bundle['coupon-help.html'] = article.encode('utf-8')
    # Production keeps its reviewed security headers; candidate-wide noindex
    # must never replace the normal site's headers.
    del bundle['_headers']
    return bundle
