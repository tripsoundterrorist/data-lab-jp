"""In-memory, noindex review bundle. Not called by the deployment build."""
from scripts.coupon_help_public_candidate import render_candidate


CONSENT_CSP = (
    "default-src 'none'; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' https://www.googletagmanager.com; "
    "connect-src 'self' https://*.google-analytics.com "
    "https://*.analytics.google.com https://*.googletagmanager.com; "
    "base-uri 'none'; form-action 'none'"
)
PRICE_LINK = (
    '<p>クーポンが使えないときは、'
    '<a href="/coupon-help" style="color:#ffffff; text-decoration:underline;">'
    '画面の状態から確認する方法</a>をご覧ください。</p>\n'
)
REQUIRED_INPUTS = frozenset({
    'preview/coupon-help.html', 'column-price.html', 'sitemap.xml',
    'analytics-consent.js', 'analytics-consent.css',
})


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('CANDIDATE_SOURCE_CHANGED')
    return text.replace(old, new, 1)


def build_candidate_bundle(sources: dict[str, bytes]) -> dict[str, bytes]:
    """Return a separate review artifact; never write dist or modify sources.

    Consent assets must be the repository's reviewed versions. Do not serve this
    analytics-enabled variant for a live test without separate send approval.
    Sitemap inclusion is for review only; every route retains noindex headers.
    """
    if set(sources) != REQUIRED_INPUTS:
        raise ValueError('CANDIDATE_INPUT_SET_MISMATCH')
    draft = sources['preview/coupon-help.html'].decode('utf-8')
    candidate = render_candidate(draft)
    candidate = _replace_once(
        candidate,
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        CONSENT_CSP,
    )
    candidate = _replace_once(candidate, '</head>',
        '  <link rel="stylesheet" href="/analytics-consent.css">\n'
        '  <script src="/analytics-consent.js" defer></script>\n</head>')
    price = sources['column-price.html'].decode('utf-8')
    if 'href="/coupon-help"' in price:
        raise ValueError('CANDIDATE_LINK_ALREADY_PRESENT')
    price = _replace_once(price, '        <a class="back" href="/">',
        '        ' + PRICE_LINK + '        <a class="back" href="/">')
    sitemap = sources['sitemap.xml'].decode('utf-8')
    if '/coupon-help' in sitemap:
        raise ValueError('CANDIDATE_SITEMAP_ALREADY_PRESENT')
    sitemap = _replace_once(sitemap, '</urlset>',
        '  <url><loc>https://datalabx.jp/coupon-help</loc></url>\n</urlset>')
    return {
        'coupon-help.html': candidate.encode('utf-8'),
        'column-price.html': price.encode('utf-8'),
        'sitemap.xml': sitemap.encode('utf-8'),
        'analytics-consent.js': sources['analytics-consent.js'],
        'analytics-consent.css': sources['analytics-consent.css'],
        '_headers': b'/*\n  X-Robots-Tag: noindex, nofollow\n',
    }
