from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RevenueMvpSecurityHeadersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.headers = (ROOT / "_headers").read_text(encoding="utf-8")

    def test_global_static_asset_rule_is_used(self):
        self.assertEqual(self.headers.splitlines()[0], "/*")

    def test_baseline_security_headers_are_present(self):
        for header in (
            "X-Content-Type-Options: nosniff",
            "X-Frame-Options: DENY",
            "Referrer-Policy: strict-origin-when-cross-origin",
            "Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        ):
            self.assertIn(header, self.headers)

    def test_csp_is_fail_closed_and_ga4_compatible(self):
        for directive in (
            "default-src 'self'",
            "base-uri 'none'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "https://www.googletagmanager.com",
            "https://*.google-analytics.com",
            "https://*.analytics.google.com",
            "upgrade-insecure-requests",
        ):
            self.assertIn(directive, self.headers)
        self.assertNotIn("'unsafe-eval'", self.headers)
        self.assertNotIn("script-src *", self.headers)
        self.assertNotIn("connect-src *", self.headers)


if __name__ == "__main__":
    unittest.main()
