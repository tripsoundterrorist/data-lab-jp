"""Render the checked-in coupon draft for local review only; never publish it.

The proposed canonical is review metadata, not an activated route. This module
does not write files, fetch data, change build inputs, or enable analytics.
"""
from html import escape
from html.parser import HTMLParser


PROPOSED_CANONICAL = "https://datalabx.jp/coupon-help"
SITE_LINKS = (
    ("/", "DATA LABトップ"),
    ("/about", "DATA LABについて"),
    ("/disclosure", "広告・データ表示方針"),
    ("/privacy", "プライバシー"),
    ("/terms", "利用規約"),
    ("/contact", "お問い合わせ"),
)


class _SourceBoundary(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "iframe", "form", "img", "base", "object", "embed"}:
            raise ValueError("ACTIVE_SOURCE_NOT_ALLOWED")
        if any(key.startswith("on") or key in {"src", "srcset", "ping"}
               for key, _ in attrs):
            raise ValueError("ACTIVE_ATTRIBUTE_NOT_ALLOWED")


def render_candidate(draft: str) -> str:
    """Prepare trusted repository HTML; this is not an arbitrary HTML sanitizer."""
    _SourceBoundary().feed(draft)
    replacements = (
        ('<title>FANZAクーポンが使えない？画面の状態から確認しよう | DATA LAB ローカル案</title>',
         '<title>FANZAクーポンが使えない？画面の状態から確認しよう | DATA LAB</title>'),
        ('</head>', f'  <link rel="canonical" href="{PROPOSED_CANONICAL}">\n</head>'),
        ('ローカルレビュー用。解析送信・広告リンク・購入ボタンはありません。',
         '公開候補のローカル確認用。公開承認は未完了です。'
         '<nav aria-label="サイト情報">' + ' / '.join(
             f'<a href="{escape(path, quote=True)}">{escape(label)}</a>'
             for path, label in SITE_LINKS
         ) + '</nav>'),
    )
    if draft.count('<meta name="robots" content="noindex, nofollow">') != 1:
        raise ValueError("NOINDEX_REQUIRED")
    if 'rel="canonical"' in draft:
        raise ValueError("CANONICAL_ALREADY_PRESENT")
    if '未公開の下書きです。公開審査・公開承認は未完了です。' not in draft:
        raise ValueError("UNPUBLISHED_NOTICE_REQUIRED")
    for old, new in replacements:
        if draft.count(old) != 1:
            raise ValueError("DRAFT_TEMPLATE_CHANGED")
        draft = draft.replace(old, new, 1)
    return draft
