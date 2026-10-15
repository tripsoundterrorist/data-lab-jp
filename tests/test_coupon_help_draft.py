from decimal import Decimal, ROUND_FLOOR
import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = []
        self.links = []
        self.meta = []
        self.elements = []
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        self.tags.append(tag)
        if tag == 'table':
            self.current_table = []
            self.tables.append(self.current_table)
        elif tag == 'tr' and self.current_table is not None:
            self.current_row = []
            self.current_table.append(self.current_row)
        elif tag in ('td', 'th') and self.current_row is not None:
            self.current_cell = []
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs['href'])
        if tag == 'meta':
            self.meta.append(attrs)

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.current_cell is not None:
            self.current_row.append(''.join(self.current_cell).strip())
            self.current_cell = None
        elif tag == 'tr':
            self.current_row = None
        elif tag == 'table':
            self.current_table = None


def assert_example_table(case, text):
    page = ArticleParser()
    page.feed(text)
    case.assertEqual(len(page.tables), 2)
    case.assertEqual(page.tables[1], [
        ['項目', 'クーポンなし', '500円分を利用'],
        ['商品価格', '2,000円', '2,000円'],
        ['支払額', '2,000円', '1,500円'],
        ['還元ポイント', '200ポイント', '150ポイント'],
    ])


class ArticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (Path(__file__).resolve().parents[1] / 'preview' / 'coupon-help.html').read_text(encoding='utf-8')
        cls.page = ArticleParser()
        cls.page.feed(cls.text)

    def test_local_only(self):
        self.assertIn({'name': 'robots', 'content': 'noindex, nofollow'}, self.page.meta)
        self.assertNotIn('script', self.page.tags)
        self.assertNotIn('form', self.page.tags)
        self.assertNotIn('iframe', self.page.tags)
        self.assertNotIn('img', self.page.tags)
        self.assertIn('未公開の下書き', self.text)

    def test_links_and_anchors(self):
        self.assertEqual(len(self.page.ids), len(set(self.page.ids)))
        expected = {
            'https://support.dmm.co.jp/payment/article/47434',
            'https://support.dmm.co.jp/payment/article/47433',
            'https://guidance.payment.dmm.co.jp/common/coupon/index.html',
            'https://support.dmm.co.jp/payment/article/47509',
        }
        self.assertEqual({x for x in self.page.links if not x.startswith('#')}, expected)
        for link in self.page.links:
            if link.startswith('#'):
                self.assertIn(link[1:], self.page.ids)

    def test_semantics(self):
        self.assertEqual(self.page.tags.count('h1'), 1)
        self.assertEqual(self.page.tags.count('caption'), 2)
        self.assertIn('name="viewport"', self.text)
        self.assertIn('説明用の仮の条件', self.text)
        self.assertIn('1ポイント未満は切り捨て', self.text)

    def test_table_headers_and_section_labels(self):
        for tag, attrs in self.page.elements:
            if tag == 'th':
                self.assertIn(attrs.get('scope'), ('row', 'col'))
            if tag == 'section':
                self.assertIn(attrs.get('aria-labelledby'), self.page.ids)
        self.assertEqual(self.page.tags.count('section'), 4)

    def test_no_automatic_external_resources(self):
        for tag, attrs in self.page.elements:
            self.assertNotIn('src', attrs)
            self.assertNotIn('srcset', attrs)
            self.assertNotIn('ping', attrs)
            self.assertFalse(any(key.startswith('on') for key in attrs))
            if tag == 'a':
                self.assertNotIn('target', attrs)
                if attrs['href'].startswith('https:'):
                    self.assertIn('noreferrer', attrs.get('rel', '').split())
        csp = [x['content'] for x in self.page.meta if x.get('http-equiv') == 'Content-Security-Policy']
        self.assertEqual(len(csp), 1)
        self.assertIn("default-src 'none'", csp[0])
        self.assertNotIn('url(', self.text.lower())
        self.assertNotIn('@import', self.text.lower())

    def test_example_arithmetic(self):
        assert_example_table(self, self.text)
        price, coupon, points = map(Decimal, ('2000', '500', '200'))
        self.assertEqual(price - coupon, 1500)
        self.assertEqual((points * (1 - coupon / price)).to_integral_value(rounding=ROUND_FLOOR), 150)
        self.assertIn('1,500円', self.text)
        self.assertIn('150ポイント', self.text)
        self.assertEqual((Decimal('201') * (1 - coupon / price)).to_integral_value(rounding=ROUND_FLOOR), 150)

    def test_draft_excluded_from_allowlisted_build_and_local_preview(self):
        root = Path(__file__).resolve().parents[1]
        for filename, constant, forbidden in (
            ('build-static-site.py', 'ALLOWLIST', 'preview/coupon-help.html'),
            ('build-local-preview.py', 'PREVIEW_FILES', 'coupon-help.html'),
        ):
            tree = ast.parse((root / 'scripts' / filename).read_text(encoding='utf-8'))
            assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == constant for target in node.targets)]
            self.assertEqual(len(assignments), 1)
            self.assertNotIn(forbidden, ast.literal_eval(assignments[0].value))
        sitemap = (root / 'sitemap.xml').read_text(encoding='utf-8')
        self.assertNotIn('coupon-help', sitemap)
        for filename in ('index.html', 'column-price.html'):
            self.assertNotIn('coupon-help', (root / filename).read_text(encoding='utf-8'))

    def test_table_check_detects_wrong_cell_even_when_correct_value_remains_elsewhere(self):
        mutations = (
            ('<td>1,500円</td>', '<td>1,400円</td>'),
            ('<td>150ポイント</td>', '<td>200ポイント</td>'),
            ('<th scope="row">支払額</th>', '<th scope="row">商品価格</th>'),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assertEqual(self.text.count(original), 1)
                mutated = self.text.replace(original, replacement)
                with self.assertRaises(AssertionError):
                    assert_example_table(self, mutated)


if __name__ == '__main__':
    unittest.main()
