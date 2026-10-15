from pathlib import Path
from html.parser import HTMLParser
import unittest
from scripts.books_device_candidate import render_candidate, PROPOSED_CANONICAL, SITE_LINKS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'preview/books-device-review.html'


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class CandidateTests(unittest.TestCase):
    def test_metadata_footer_and_safety(self):
        result = render_candidate(SOURCE.read_bytes())
        p = Tags()
        p.feed(result)
        self.assertIn(('meta', {'name': 'robots', 'content': 'noindex, nofollow'}), p.tags)
        self.assertIn(('link', {'rel': 'canonical', 'href': PROPOSED_CANONICAL}), p.tags)
        self.assertEqual(sum(t == 'meta' and a.get('name') == 'description' for t, a in p.tags), 1)
        self.assertIn('未公開のレビュー案', result)
        for url, label in SITE_LINKS:
            self.assertIn(f'<a href="{url}">{label}</a>', result)
        for tag, attrs in p.tags:
            self.assertNotIn(tag, {'script', 'iframe', 'form', 'img', 'object', 'embed'})
            self.assertFalse(any(k.startswith('on') for k in attrs))
        self.assertNotIn('/go/', result)

    def test_modified_sources_fail_closed(self):
        source = SOURCE.read_bytes()
        for bad in (source + b'<script></script>', source.replace(b'noindex', b'index'),
                    source.replace(b'</head>', b''), b'', source + b' '):
            with self.subTest(tail=bad[-20:]):
                with self.assertRaises(ValueError):
                    render_candidate(bad)

    def test_source_unchanged_and_deterministic(self):
        source = SOURCE.read_bytes()
        self.assertEqual(render_candidate(source), render_candidate(source))
        self.assertEqual(SOURCE.read_bytes(), source)

    def test_checkout_line_endings_do_not_change_candidate(self):
        source = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(render_candidate(source), render_candidate(source.replace(b'\n', b'\r\n')))

    def test_not_connected_to_public_build(self):
        build = (ROOT / 'scripts/build-static-site.py').read_text(encoding='utf-8')
        self.assertNotIn('books_device_candidate', build)
        for name in ('sitemap.xml', 'index.html', 'column-price.html'):
            self.assertNotIn('books-device-check', (ROOT / name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
