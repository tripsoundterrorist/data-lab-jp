"""Pure local review transform for one pinned draft; not a generic sanitizer.

No filesystem writes, network access, deployment integration or analytics.
The proposed canonical is review metadata, not a published route.
"""
from hashlib import sha256
from html import escape

SOURCE_SHA256 = 'e9f84f28fc0e34be07ef5e3372adbfafd2706a2a2e066b093a8722ed49100e63'
PROPOSED_CANONICAL = 'https://datalabx.jp/books-device-check'
SITE_LINKS = (
    ('/', 'DATA LABトップ'), ('/about', 'DATA LABについて'),
    ('/disclosure', '広告・データ表示方針'), ('/privacy', 'プライバシー'),
    ('/terms', '利用規約'), ('/contact', 'お問い合わせ'),
)


def render_candidate(source: bytes) -> str:
    source = source.replace(b'\r\n', b'\n')
    if sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('REVIEWED_SOURCE_CHANGED')
    draft = source.decode('utf-8')
    replacements = (
        (' | DATA LAB 未公開レビュー案</title>', ' | DATA LAB 公開候補・未公開</title>'),
        ('</head>', '<meta name="description" content="FANZAブックスを購入する前に、作品の閲覧環境とスマホ・PCの対応を確認する手順。縦読み作品と古い端末の注意点も整理します。">\n'
         f'<link rel="canonical" href="{PROPOSED_CANONICAL}">\n</head>'),
        ('<footer>', '<footer><nav aria-label="サイト案内">' + ' / '.join(
            f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
            for url, label in SITE_LINKS) + '</nav>'),
    )
    for old, new in replacements:
        if draft.count(old) != 1:
            raise ValueError('DRAFT_TEMPLATE_CHANGED')
        draft = draft.replace(old, new, 1)
    return draft
