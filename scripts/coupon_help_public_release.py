"""Public artifact transform. Local code readiness is not deployment approval."""
from scripts.coupon_help_candidate_bundle import build_candidate_bundle, _replace_once


RELATED_PRICE_LINK = (
    '<p class="related">FANZA動画の価格を比べるときは、'
    '<a href="/column-price">支払額と視聴条件の確認ポイント</a>'
    'もご覧ください。</p>\n'
)

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
    if 'href="/column-price"' in article:
        raise ValueError('RELATED_PRICE_LINK_ALREADY_PRESENT')
    article = _replace_once(article, '  </article></main>', '  ' + RELATED_PRICE_LINK + '  </article></main>')
    bundle['coupon-help.html'] = article.encode('utf-8')
    # Production keeps its reviewed security headers; candidate-wide noindex
    # must never replace the normal site's headers.
    del bundle['_headers']
    return bundle
