"""Offline entry-copy checks; no browser execution, network or publication."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

from scripts.article_navigation_local_build import collect_local_bundle

ROOT = Path(__file__).resolve().parents[1]
NOTICE = ('FANZA動画の商品情報を、確認時点の記録として掲載しています。'
          '掲載価格は現在の購入価格を保証しません。'
          '最新の価格・条件は公式商品ページで確認してください。')


class NoticeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class ItemsEntryNoticeTests(unittest.TestCase):
    def assert_notice(self, source):
        marker = '<p class="notice">' + NOTICE + '</p>'
        self.assertEqual(source.count(marker), 1)
        self.assertLess(source.index('<main id="main-content">'), source.index(marker))
        self.assertLess(source.index(marker), source.index('<section class="controls panel"'))
        self.assertLess(source.index(marker), source.index('<section class="item-grid"'))
        parsed = NoticeParser()
        parsed.feed(marker)
        self.assertEqual(parsed.tags, [('p', {'class': 'notice'})])
        self.assertEqual(source.count('<article class="item">'), 100)

    def test_source_notice_precedes_controls_and_cards(self):
        self.assert_notice((ROOT / 'items/index.html').read_text(encoding='utf-8'))

    def test_default_and_navigation_builds_preserve_notice(self):
        for enabled in (False, True):
            with self.subTest(navigation=enabled):
                files = collect_local_bundle(enabled=enabled)
                self.assert_notice(files['items/index.html'].decode('utf-8'))
                self.assertEqual(len(files), 27 if enabled else 23)
                self.assertEqual(files['items/index.html'], (ROOT / 'items/index.html').read_bytes())


if __name__ == '__main__':
    unittest.main()
