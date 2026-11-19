"""Default-off in-memory coupon calculator review. No public build hook or I/O writes.

Opt-in output retains baseline live-capable analytics. Do not serve or execute it
without separate transmission authority. Tests supply an inert DOM only.
"""
from html.parser import HTMLParser
from pathlib import Path

SOURCE_ASSETS = {
    'fragment': 'preview/coupon-calculator-fragment.html',
    'css': 'preview/coupon-calculator.css',
    'js': 'runtime-candidates/coupon-calculator-candidate.js',
}
OUTPUT_CSS = 'coupon-calculator/candidate.css'
OUTPUT_JS = 'coupon-calculator/candidate.js'
ROOT_ID = 'datalab-coupon-calculator'
ANCHOR = '    </section>\n    <p class="note"><strong>最後に確認するのは、'
TAGS = ('<link rel="stylesheet" href="/coupon-calculator/candidate.css">\n'
        '<script src="/coupon-calculator/candidate.js" defer></script>\n')
NOINDEX = '<meta name="robots" content="noindex, nofollow">\n'
HEADERS = b'\n/*\n  X-Robots-Tag: noindex, nofollow\n'


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.refs = []
        self.robots = []
        self.active = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            self.ids.append(values['id'])
        for key in ('for', 'aria-describedby', 'aria-labelledby'):
            self.refs.extend(values.get(key, '').split())
        if tag == 'meta' and values.get('name') == 'robots':
            self.robots.append(values.get('content', ''))
        if tag in {'script', 'iframe', 'object', 'embed', 'base', 'a', 'img', 'link'}:
            self.active = True
        if any(key.startswith('on') or key in {'src', 'href', 'action', 'formaction', 'ping', 'srcset'}
               for key, _ in attrs):
            self.active = True


def collect_assets(source_root):
    """Explicit read of three reviewed files; reject linked paths."""
    source = Path(source_root)
    if any(part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction())
           for part in (source, *source.parents)):
        raise ValueError('CALCULATOR_LINKED_SOURCE')
    root = source.resolve(strict=True)
    result = {}
    for key, relative in SOURCE_ASSETS.items():
        path = root / relative
        if any(part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction())
               for part in (path, *path.parents)):
            raise ValueError('CALCULATOR_LINKED_SOURCE')
        resolved = path.resolve(strict=True)
        if root not in resolved.parents or not resolved.is_file():
            raise ValueError('CALCULATOR_SOURCE_INVALID')
        result[key] = resolved.read_bytes()
    return result


def build_candidate_bundle(baseline, assets, *, enabled=False):
    """Pure opt-in review transform; no filesystem, server, analytics or publication."""
    if type(enabled) is not bool:
        raise ValueError('EXPLICIT_BOOLEAN_REQUIRED')
    result = dict(baseline)
    if not enabled:
        return result
    if set(assets) != set(SOURCE_ASSETS) or not {'coupon-help.html', '_headers'} <= set(baseline):
        raise ValueError('CALCULATOR_INPUT_SET_MISMATCH')
    if any(name.startswith('coupon-calculator/') for name in baseline):
        raise ValueError('CALCULATOR_PRISTINE_BASELINE_REQUIRED')
    if any(not isinstance(value, bytes) for value in (*baseline.values(), *assets.values())):
        raise ValueError('CALCULATOR_BYTES_REQUIRED')
    article = baseline['coupon-help.html'].decode('utf-8')
    fragment = assets['fragment'].decode('utf-8')
    if ROOT_ID in article or '/coupon-calculator/' in article:
        raise ValueError('CALCULATOR_PRISTINE_BASELINE_REQUIRED')
    if article.count(ANCHOR) != 1 or article.count('</head>') != 1:
        raise ValueError('CALCULATOR_ARTICLE_ANCHOR_CHANGED')
    original, widget = _Markup(), _Markup()
    original.feed(article)
    widget.feed(fragment)
    if (widget.active or widget.ids.count(ROOT_ID) != 1
            or len(widget.ids) != len(set(widget.ids))
            or set(original.ids) & set(widget.ids)
            or not set(widget.refs) <= set(widget.ids)):
        raise ValueError('CALCULATOR_FRAGMENT_INVALID')
    if len(original.robots) > 1:
        raise ValueError('CALCULATOR_ROBOTS_CHANGED')
    if original.robots and 'noindex' not in original.robots[0].lower().replace(' ', '').split(','):
        raise ValueError('CALCULATOR_ROBOTS_CHANGED')
    if not original.robots:
        article = article.replace('</head>', NOINDEX + '</head>', 1)
    article = article.replace(ANCHOR, '    </section>\n' + fragment
                              + '    <p class="note"><strong>最後に確認するのは、', 1)
    article = article.replace('</head>', TAGS + '</head>', 1)
    result['coupon-help.html'] = article.encode('utf-8')
    result['_headers'] = baseline['_headers'] + HEADERS
    result[OUTPUT_CSS] = assets['css']
    result[OUTPUT_JS] = assets['js']
    return result
