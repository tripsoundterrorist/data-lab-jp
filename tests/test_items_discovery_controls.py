from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DiscoveryControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "items" / "discovery.js").read_text(encoding="utf-8")

    def test_is_local_dom_only_and_has_no_network_or_affiliate_data(self):
        for forbidden in ("fetch(", "XMLHttpRequest", "affiliateURL", "DMM_AFFILIATE_ID", "localStorage"):
            self.assertNotIn(forbidden, self.source)

    def test_supports_required_filters_and_stable_sorts(self):
        for required in (
            "#item-search", "#price-filter", "#item-sort", "under-1000",
            "1000-1999", "2000-2999", "3000-plus", "price-asc",
            "price-desc", "observed-desc", "observed-asc", "left.index - right.index",
        ):
            self.assertIn(required, self.source)

    def test_fail_soft_keeps_server_rendered_cards_without_controls(self):
        self.assertIn("if (!grid || !search || !priceFilter || !sort || !resultCount || !pageStatus) return;", self.source)
        self.assertNotIn("innerHTML", self.source)

    def test_hidden_cards_override_existing_flex_layout(self):
        css = (ROOT / "items" / "items.css").read_text(encoding="utf-8")
        self.assertIn(".item[hidden] { display: none; }", css)


if __name__ == "__main__":
    unittest.main()
