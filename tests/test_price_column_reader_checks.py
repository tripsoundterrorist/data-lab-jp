"""Reader-facing copy assertions; no analytics, network or publication."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PriceColumnReaderChecksTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "column-price.html").read_text(encoding="utf-8")

    def test_coupon_and_final_amount_are_confirmed_not_promised(self):
        self.assertIn("クーポンなどを使う場合は、適用条件も確認しましょう。", self.text)
        self.assertIn("購入確認画面で、自分が選んだ内容と支払額が想定どおりかを確かめてください。", self.text)
        self.assertIn("2,000円の商品が50％OFFなら1,000円", self.text)
        self.assertIn("1,200円の商品が20％OFFなら960円", self.text)
        self.assertIn("実際の商品価格やセール情報ではありません", self.text)

    def test_three_step_checklist_is_semantic_and_actionable(self):
        match = re.search(r'<h2>迷ったら、3つを順番に確認</h2>\s*<ul>(.*?)</ul>', self.text, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(re.findall(r'<li>(.*?)</li>', match[1], re.S), [
            "自分が選んだ内容の支払額",
            "再生方法・画質・視聴期限と対応端末",
            "価格の確認日時と、公式ページの現在の表示",
        ])

    def test_lower_bound_faq_is_hypothetical_and_not_a_purchase_guarantee(self):
        self.assertEqual(self.text.count('<h2>「980円〜」なら980円で買える？</h2>'), 1)
        self.assertIn("この表示だけでは、自分が選ぶ内容の購入金額は確定しません。", self.text)
        self.assertIn("「980円〜」は説明用の例で、特定の商品やサービスの価格・販売条件を示すものではありません。", self.text)
        self.assertIn("古い掲載価格で購入できると考えず、現在の条件を確認してください。", self.text)
        self.assertNotIn('"@type":"FAQPage"', self.text)


if __name__ == "__main__":
    unittest.main()
