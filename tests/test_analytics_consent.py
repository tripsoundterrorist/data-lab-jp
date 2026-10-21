from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRACKED_PAGES = (
    "index.html",
    "column-price.html",
    "column-score.html",
    "column-trend.html",
    "about.html",
    "disclosure.html",
    "privacy.html",
    "terms.html",
    "contact.html",
    "items/index.html",
    "items/item.html",
)


class AnalyticsConsentTests(unittest.TestCase):
    def setUp(self):
        self.script = (ROOT / "analytics-consent.js").read_text(encoding="utf-8")

    def require_node(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        return node

    def test_tracked_pages_load_only_local_consent_bootstrap(self):
        for page in TRACKED_PAGES:
            document = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertIn('href="/analytics-consent.css"', document)
                self.assertIn('src="/analytics-consent.js"', document)
                self.assertNotIn("googletagmanager.com", document)
                self.assertNotIn("G-ZPBQJ6137L", document)

    def test_google_script_is_created_only_after_persisted_grant(self):
        self.assertIn('if (analyticsLoaded || readChoice() !== GRANTED) return;', self.script)
        self.assertIn('if (!saveChoice(GRANTED)) return;', self.script)
        self.assertIn("document.createElement(\"script\")", self.script)
        self.assertIn("googletagmanager.com/gtag/js", self.script)

    def test_all_advertising_consent_defaults_are_denied(self):
        for setting in ("ad_storage", "ad_user_data", "ad_personalization"):
            self.assertIn(f'{setting}: "denied"', self.script)
        self.assertIn("allow_google_signals: false", self.script)
        self.assertIn("allow_ad_personalization_signals: false", self.script)

    def test_invalid_or_unavailable_storage_fails_closed(self):
        self.assertIn("return value === GRANTED || value === DENIED ? value : null;", self.script)
        self.assertIn("catch (_) {\n      return null;", self.script)
        self.assertIn("catch (_) {\n      return false;", self.script)

    def test_runtime_consent_boundary_in_node_harness(self):
        result = subprocess.run(
            [
                self.require_node(),
                str(ROOT / "tests" / "analytics_consent_runtime_harness.js"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_javascript_is_syntactically_valid(self):
        result = subprocess.run(
            [self.require_node(), "--check", str(ROOT / "analytics-consent.js")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_privacy_notice_matches_implementation(self):
        privacy = (ROOT / "privacy.html").read_text(encoding="utf-8")
        self.assertIn("許可するまではGoogle Analyticsのスクリプトを読み込まず", privacy)
        self.assertIn("localStorage", privacy)
        self.assertIn("アクセス解析設定", privacy)

    def assert_event_notice_matches_implementation(self, privacy):
        notice = (
            "同意後は、ページ表示や商品・記事の導線利用を計測します。"
            "商品用イベントには当サイトの商品管理IDと表示場所を、"
            "記事間クリックには導線区分を付加します。"
            "商品名、外部商品URL、検索語、価格は、"
            "これらの独自イベントの追加項目として付加しません。"
        )
        self.assertIn(notice, privacy)
        self.assertNotIn("商品名、商品URL、商品ID、検索語、価格を付加しません", privacy)
        self.assertIn("return { item_id: value.public_id, funnel_surface: value.surface };", self.script)
        bridge = (ROOT / "runtime-candidates" / "article-navigation-ga4-bridge-candidate.mjs").read_text(encoding="utf-8")
        self.assertIn("navigation_route: label", bridge)
        self.assertIn('readConsent() !== "granted"', bridge)

    def test_privacy_event_notice_discloses_management_id_surface_and_navigation(self):
        privacy = (ROOT / "privacy.html").read_text(encoding="utf-8")
        self.assert_event_notice_matches_implementation(privacy)

    def test_privacy_event_notice_rejects_old_or_incomplete_description(self):
        privacy = (ROOT / "privacy.html").read_text(encoding="utf-8")
        for old, replacement in (
            ("当サイトの商品管理IDと表示場所", "表示場所"),
            ("記事間クリックには導線区分を付加します。", ""),
            ("これらの独自イベントの追加項目として", "一切"),
            ("</main>", "<p>商品名、商品URL、商品ID、検索語、価格を付加しません。</p></main>"),
        ):
            with self.subTest(description=old):
                self.assertIn(old, privacy)
                with self.assertRaises(AssertionError):
                    self.assert_event_notice_matches_implementation(privacy.replace(old, replacement, 1))

    def test_funnel_events_and_product_context_are_strictly_allowlisted(self):
        for event in (
            "view_item_list", "select_item", "view_item",
            "outbound_product_click",
        ):
            self.assertIn(f'"{event}"', self.script)
        self.assertIn("!ALLOWED_EVENTS.has(name)", self.script)
        self.assertIn('window.gtag("event", name);', self.script)
        self.assertIn('window.gtag("event", name, parameters);', self.script)
        self.assertIn('!/^itm_[0-9a-f]{24}$/.test(value.public_id)', self.script)
        self.assertIn('ALLOWED_SURFACES.has(value.surface)', self.script)
        self.assertNotIn("item_name", self.script)

    def test_event_tracking_requires_current_granted_consent(self):
        self.assertIn("readChoice() !== GRANTED", self.script)
        self.assertIn('typeof window.gtag !== "function"', self.script)
        self.assertIn("Object.freeze({ trackEvent })", self.script)

    def test_page_view_strips_query_fragment_and_referrer(self):
        self.assertIn("send_page_view: false", self.script)
        self.assertIn(
            "page_location: window.location.origin + window.location.pathname",
            self.script,
        )
        self.assertIn("page_path: window.location.pathname", self.script)
        self.assertIn('page_referrer: ""', self.script)
        self.assertIn("window.location.search", self.script)
        self.assertNotIn("window.location.hash", self.script)

    def test_only_strict_x_campaign_parameters_are_forwarded(self):
        for value in (
            'source[0] !== "x"', 'medium[0] !== "social"',
            'campaign_source: "x"', 'campaign_medium: "social"',
            "campaign_name: campaign[0]",
        ):
            self.assertIn(value, self.script)
        self.assertIn('source.length !== 1', self.script)
        self.assertIn('campaign.length !== 1', self.script)
        self.assertNotIn("page_location: window.location.href", self.script)


if __name__ == "__main__":
    unittest.main()
