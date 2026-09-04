from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RevenueMvpItemUiTests(unittest.TestCase):
    def setUp(self):
        self.index = (ROOT / "items/index.html").read_text(encoding="utf-8")
        self.detail = (ROOT / "items/item.html").read_text(encoding="utf-8")
        self.script = (ROOT / "items/items.js").read_text(encoding="utf-8")

    def test_unreleased_item_routes_remain_noindex(self):
        for document in (self.index, self.detail):
            self.assertIn('name="robots" content="noindex,nofollow"', document)

    def test_item_routes_use_production_canonicals(self):
        self.assertIn('href="https://datalabx.jp/items/"', self.index)
        self.assertIn('href="https://datalabx.jp/items/item.html"', self.detail)
        self.assertNotIn("pages.dev", self.index + self.detail)

    def test_item_routes_link_required_site_information(self):
        for document in (self.index, self.detail):
            for path in ("about", "disclosure", "privacy", "terms", "contact"):
                self.assertIn(f'href="/{path}.html"', document)

    def test_external_product_link_is_explicit_and_safe(self):
        self.assertIn("公式商品ページを見る（外部サイト）", self.script)
        self.assertIn('official.rel = "noopener noreferrer"', self.script)
        self.assertNotIn('official.rel = "sponsored', self.script)

    def test_detail_discloses_independent_observation_scope(self):
        self.assertIn("DMM/FANZA公式のランキングや作品評価ではありません", self.script)
        self.assertIn('policy.href = "/disclosure.html"', self.script)

    def test_affiliate_url_is_not_read_by_browser_code(self):
        self.assertNotIn("affiliate_url", self.script.casefold())
        self.assertNotIn("affiliateid", self.script.casefold())


if __name__ == "__main__":
    unittest.main()
