"""The device article remains a passive, non-deployed review draft."""
import ast
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class BooksDeviceDraftTests(unittest.TestCase):
    def test_passive_unpublished_document(self):
        source = (ROOT / 'preview/books-device-review.html').read_text(encoding='utf-8')
        parser = Tags()
        parser.feed(source)
        self.assertIn('未公開', source)
        self.assertIn(('meta', {'name': 'robots', 'content': 'noindex, nofollow'}), parser.tags)
        for tag, attrs in parser.tags:
            self.assertNotIn(tag, {'script', 'iframe', 'form', 'img', 'base', 'object', 'embed'})
            self.assertFalse(any(key.startswith('on') for key in attrs))
            self.assertNotIn('canonical', attrs.get('rel', '').lower().split())
            if tag == 'a':
                self.assertTrue(attrs['href'].startswith(('#', 'https://support.dmm.co.jp/book/article/')))

    def test_anchors_resolve(self):
        parser = Tags()
        parser.feed((ROOT / 'preview/books-device-review.html').read_text(encoding='utf-8'))
        ids = [attrs['id'] for _, attrs in parser.tags if 'id' in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for tag, attrs in parser.tags:
            if tag == 'a' and attrs.get('href', '').startswith('#'):
                self.assertIn(attrs['href'][1:], ids)

    def test_not_in_build_or_public_navigation(self):
        tree = ast.parse((ROOT / 'scripts/build-static-site.py').read_text(encoding='utf-8'))
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'ALLOWLIST' for t in node.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertFalse(any('books-device' in value for value in ast.literal_eval(assignments[0].value)))
        for name in ('sitemap.xml', 'index.html', 'column-price.html'):
            self.assertNotIn('books-device', (ROOT / name).read_text(encoding='utf-8'))

    def test_actual_build_dry_run_excludes_draft(self):
        result = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'scripts/build-static-site.py'), '--dry-run'],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Mode: dry-run', result.stdout)
        self.assertIn('Validation: passed', result.stdout)
        self.assertNotIn('books-device', result.stdout)

    def test_title_and_heading_match_reviewed_copy(self):
        source = (ROOT / 'preview/books-device-review.html').read_text(encoding='utf-8')
        title = 'FANZAブックスを買う前に｜スマホ・PCで読むための確認'
        self.assertIn(f'<title>{title} | DATA LAB 未公開レビュー案</title>', source)
        self.assertIn(f'<h1>{title}</h1>', source)
        self.assertEqual(source.count('<h1>'), 1)
