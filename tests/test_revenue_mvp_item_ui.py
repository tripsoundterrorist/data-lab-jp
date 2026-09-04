from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RevenueMvpItemUiTests(unittest.TestCase):
    def setUp(self):
        self.index = (ROOT / "items/index.html").read_text(encoding="utf-8")
        self.detail = (ROOT / "items/item.html").read_text(encoding="utf-8")
        self.script = (ROOT / "items/items.js").read_text(encoding="utf-8")
        self.styles = (ROOT / "items/items.css").read_text(encoding="utf-8")

    def test_item_routes_support_keyboard_navigation(self):
        for document in (self.index, self.detail):
            self.assertIn('class="skip-link" href="#main-content"', document)
            self.assertIn('<main id="main-content">', document)
        self.assertIn(":focus-visible", self.styles)
        self.assertIn("outline: 3px solid #fff", self.styles)

    def test_mobile_controls_have_minimum_touch_targets(self):
        for selector in (
            ".controls input, .controls select",
            ".detail-link, .back-link",
            ".pagination button",
            ".comparison-toggle",
            ".official-link",
            ".policy-link",
        ):
            rule = self.styles.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("min-height: 44px", rule)

    def test_dynamic_results_use_bounded_live_regions(self):
        self.assertIn('id="result-count" role="status" aria-live="polite"', self.index)
        self.assertIn('id="page-status" aria-live="polite"', self.index)
        self.assertNotIn('id="item-grid" class="item-grid" aria-live=', self.index)
        self.assertNotIn('id="detail-root" class="detail-root" aria-live=', self.detail)

    def test_narrow_layout_reduces_padding_and_wraps_titles(self):
        self.assertIn("@media (max-width: 430px)", self.styles)
        self.assertIn("main { padding-inline: 14px; }", self.styles)
        self.assertIn("overflow-wrap: anywhere", self.styles)

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

    def test_funnel_events_run_only_after_public_data_validation(self):
        self.assertGreater(
            self.script.index('trackFunnelEvent("view_item_list")'),
            self.script.index("validateManifest(manifest)"),
        )
        self.assertGreater(
            self.script.index('trackFunnelEvent("view_item")'),
            self.script.rindex("validateManifest(manifest)"),
        )
        self.assertIn('trackFunnelEvent("select_item")', self.script)
        self.assertIn('trackFunnelEvent("outbound_product_click")', self.script)

    def test_funnel_events_do_not_send_product_attributes(self):
        calls = re.findall(r'trackFunnelEvent\(([^)]*)\)', self.script)[1:]
        self.assertTrue(calls)
        self.assertTrue(all(re.fullmatch(r'"[a-z_]+"', arguments) for arguments in calls))

    def test_runtime_revalidates_items_before_rendering(self):
        self.assertIn("index.items.every(validateIndexItem)", self.script)
        self.assertIn("validateDetailItem(detail.item)", self.script)
        self.assertGreater(
            self.script.index("state.items = index.items.slice()"),
            self.script.index("index.items.every(validateIndexItem)"),
        )
        self.assertGreater(
            self.script.index("renderDetail(detail.item)"),
            self.script.index("validateDetailItem(detail.item)"),
        )

    def test_runtime_url_validation_rejects_active_and_local_targets(self):
        self.assertIn('["http:", "https:"]', self.script)
        self.assertIn('host !== "localhost"', self.script)
        self.assertIn('!host.endsWith(".localhost")', self.script)
        self.assertIn('!host.startsWith("127.")', self.script)
        self.assertIn("!parsed.username && !parsed.password", self.script)
        self.assertIn("safePublicUrl(item.image_url)", self.script)
        self.assertIn("safePublicUrl(item.item_url)", self.script)

    def test_runtime_schema_rejects_unknown_item_fields(self):
        self.assertIn("Object.keys(value).length === expected.length", self.script)
        self.assertIn("expected.every((key) => Object.hasOwn(value, key))", self.script)
        self.assertIn('exactKeys(index, ["public_schema_version", "generated_at", "as_of", "items"])', self.script)
        self.assertIn('exactKeys(detail, ["public_schema_version", "generated_at", "as_of", "item"])', self.script)
        self.assertIn("new Set(index.items.map", self.script)


if __name__ == "__main__":
    unittest.main()
