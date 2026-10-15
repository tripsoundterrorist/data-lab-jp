"""In-memory release/rollback transform; ordinary build is disabled by default.

Always supply the pristine baseline output. enabled=False rebuilds that baseline,
removing article/link/sitemap changes together. Never patch deployed output in
place. Returned public-form HTML is a local artifact, not publication authority.
"""
from scripts.books_device_candidate import render_candidate, PROPOSED_CANONICAL
from scripts.coupon_help_candidate_bundle import CONSENT_CSP

ARTICLE = 'books-device-check.html'
ROUTE = '/books-device-check'
LINK = ('<p>購入前に、<a href="/books-device-check">'
        'スマホ・PCで読むための確認ポイント</a>もご覧ください。</p>\n')


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('RELEASE_TEMPLATE_CHANGED')
    return text.replace(old, new, 1)


def build_release_bundle(baseline: dict[str, bytes], source: bytes,
                         *, enabled: bool = False) -> dict[str, bytes]:
    if type(enabled) is not bool:
        raise ValueError('EXPLICIT_BOOLEAN_REQUIRED')
    if not {'column-price.html', 'sitemap.xml', '_headers'} <= baseline.keys():
        raise ValueError('BASELINE_INPUTS_MISSING')
    if ARTICLE in baseline or any(ROUTE.encode() in baseline[name]
                                 for name in ('column-price.html', 'sitemap.xml')):
        raise ValueError('PRISTINE_BASELINE_REQUIRED')
    result = dict(baseline)
    if not enabled:
        return result
    if not {'analytics-consent.js', 'analytics-consent.css'} <= baseline.keys():
        raise ValueError('CONSENT_ASSETS_MISSING')
    article = render_candidate(source)
    replacements = (
        ('<meta name="robots" content="noindex, nofollow">\n', ''),
        (' | DATA LAB 公開候補・未公開</title>', ' | DATA LAB</title>'),
        ('<aside class="notice">未公開のレビュー案です。公式サイトではありません。広告リンク・購入ボタン・画像・アクセス解析は含みません。</aside>',
         '<aside class="notice">公式サイトではありません。公式案内をもとに、購入前の確認手順を整理しています。</aside>'),
        ('DATA LAB ローカルレビュー用。公開承認・実機での動作保証を示すものではありません。',
         'DATA LAB。実機での動作を保証するものではありません。'),
    )
    for old, new in replacements:
        article = replace_once(article, old, new)
    article = replace_once(article,
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        CONSENT_CSP)
    article = replace_once(article, '</head>',
        '<link rel="stylesheet" href="/analytics-consent.css">\n'
        '<script src="/analytics-consent.js" defer></script>\n</head>')
    price = replace_once(baseline['column-price.html'].decode('utf-8'),
                         '        <a class="back" href="/">',
                         '        ' + LINK + '        <a class="back" href="/">')
    sitemap = replace_once(baseline['sitemap.xml'].decode('utf-8'), '</urlset>',
                           f'  <url><loc>{PROPOSED_CANONICAL}</loc></url>\n</urlset>')
    result.update({ARTICLE: article.encode('utf-8'),
                   'column-price.html': price.encode('utf-8'),
                   'sitemap.xml': sitemap.encode('utf-8')})
    return result
