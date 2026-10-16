"""Bounded search-entry copy checks; no network or publication."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SearchEntryCopyTests(unittest.TestCase):
    def test_home_metadata_is_consistent_and_describes_available_features(self):
        text = (ROOT / "index.html").read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", text)[1]
        self.assertEqual(title, "作品を価格・名前で探す | DATA LAB")
        self.assertIn(f'property="og:title" content="{title}"', text)
        description = re.search(r'name="description" content="([^"]+)"', text)[1]
        self.assertIn("名前や価格帯で絞り込めます", description)
        self.assertIn("掲載価格は現在の価格を保証しません", description)
        self.assertIn(f'property="og:description" content="{description}"', text)
        structured = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text)[1])
        self.assertEqual(structured["description"], description)

    def test_price_article_has_one_contextual_list_link(self):
        text = (ROOT / "column-price.html").read_text(encoding="utf-8")
        self.assertEqual(text.count('href="/items/"'), 1)
        self.assertIn("掲載情報は確認時点の記録です。現在の価格・条件は公式ページでご確認ください。", text)
        self.assertIn('<a href="/items/" style="color:#ffffff; text-decoration:underline;">FANZA動画の作品一覧を見る</a>', text)
        self.assertNotIn("coupon-help", text)


if __name__ == "__main__":
    unittest.main()
