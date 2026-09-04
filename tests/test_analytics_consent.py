from pathlib import Path
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

    def test_javascript_is_syntactically_valid(self):
        result = subprocess.run(
            ["node", "--check", str(ROOT / "analytics-consent.js")],
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

    def test_funnel_events_are_strictly_allowlisted_and_parameter_free(self):
        for event in (
            "view_item_list", "select_item", "view_item",
            "outbound_product_click",
        ):
            self.assertIn(f'"{event}"', self.script)
        self.assertIn("!ALLOWED_EVENTS.has(name)", self.script)
        self.assertIn('window.gtag("event", name);', self.script)
        self.assertNotIn('window.gtag("event", name,', self.script)

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
        self.assertNotIn("window.location.search", self.script)
        self.assertNotIn("window.location.hash", self.script)


if __name__ == "__main__":
    unittest.main()
