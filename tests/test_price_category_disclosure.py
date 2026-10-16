from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PriceCategoryDisclosureTests(unittest.TestCase):
    def test_category_disclosed_before_product_link(self):
        source = (ROOT / 'column-price.html').read_text(encoding='utf-8')
        notice = '現在の作品一覧はFANZA動画が対象です。FANZAブックスの作品は掲載していません。'
        label = 'FANZA動画の作品一覧を見る'
        self.assertEqual(source.count(notice), 1)
        self.assertEqual(source.count('href="/items/"'), 1)
        self.assertEqual(source.count(label), 1)
        self.assertLess(source.index(notice), source.index('href="/items/"'))
        self.assertIn('rel="canonical" href="https://datalabx.jp/column-price"', source)

    def test_product_link_stays_internal_and_has_explicit_label(self):
        links = []
        class Links(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    links.append(dict(attrs))
        Links().feed((ROOT / 'column-price.html').read_text(encoding='utf-8'))
        selected = [link for link in links if link.get('href') == '/items/']
        self.assertEqual(len(selected), 1)
        self.assertNotIn('onclick', selected[0])


if __name__ == '__main__':
    unittest.main()
