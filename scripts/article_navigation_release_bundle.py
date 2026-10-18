"""Default-off, in-memory navigation transform. Readiness is not publication authority."""
from pathlib import Path

PAGES = ('coupon-help.html', 'books-device-check.html', 'column-price.html')
MODULES = (
    'article-navigation-analytics-candidate.mjs',
    'article-navigation-dom-adapter-candidate.mjs',
    'article-navigation-ga4-bridge-candidate.mjs',
)
ASSETS = {f'article-navigation/{name}': name for name in MODULES}
ASSETS['article-navigation/bootstrap.mjs'] = 'article-navigation-bootstrap-candidate.mjs'
TAG = '<script type="module" src="/article-navigation/bootstrap.mjs"></script>\n'
CONSENT_OLD = 'window.dataLabAnalytics = Object.freeze({ trackEvent });'
CONSENT_NEW = 'window.dataLabAnalytics = Object.freeze({ trackEvent, readConsent: readChoice });'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('NAVIGATION_TEMPLATE_CHANGED')
    return text.replace(old, new, 1)


def build_navigation_bundle(baseline, assets, *, enabled=False):
    if type(enabled) is not bool:
        raise ValueError('EXPLICIT_BOOLEAN_REQUIRED')
    result = dict(baseline)
    if not enabled:
        return result
    if set(assets) != set(ASSETS) or not set(PAGES + ('analytics-consent.js',)) <= set(baseline):
        raise ValueError('NAVIGATION_INPUTS_MISSING')
    if any(name.startswith('article-navigation/') for name in baseline):
        raise ValueError('PRISTINE_BASELINE_REQUIRED')
    if any(b'/article-navigation/' in baseline[name] for name in PAGES):
        raise ValueError('PRISTINE_BASELINE_REQUIRED')
    consent = baseline['analytics-consent.js'].decode('utf-8')
    result['analytics-consent.js'] = replace_once(consent, CONSENT_OLD, CONSENT_NEW).encode('utf-8')
    for name in PAGES:
        html = replace_once(baseline[name].decode('utf-8'), '</head>', TAG + '</head>')
        if name == 'books-device-check.html':
            html = replace_once(html, '<a href="/column-price">',
                                '<a data-datalab-article-navigation="true" href="/column-price">')
        result[name] = html.encode('utf-8')
    result.update(assets)
    return result


def collect_assets(source_root):
    root = Path(source_root).resolve(strict=True)
    result = {}
    for output_name, filename in ASSETS.items():
        path = root / 'runtime-candidates' / filename
        if any(part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction())
               for part in (path, *path.parents)):
            raise ValueError('NAVIGATION_SOURCE_SYMLINK_FORBIDDEN')
        resolved = path.resolve(strict=True)
        if root not in resolved.parents or not resolved.is_file():
            raise ValueError('NAVIGATION_SOURCE_INVALID')
        result[output_name] = resolved.read_bytes()
    return result
