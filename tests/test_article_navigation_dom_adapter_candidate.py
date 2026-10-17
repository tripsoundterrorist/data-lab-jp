"""Offline DOM-like clicks only; no browser, network or analytics transport."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ArticleNavigationDomAdapterTests(unittest.TestCase):
    def test_mock_clicks_consent_failures_and_cleanup(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not available')
        result = subprocess.run(
            [node, str(ROOT / 'tests/article_navigation_dom_adapter_harness.mjs')],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_public_integration_or_transport(self):
        token = 'article-navigation-dom-adapter-candidate'
        for path in ('scripts/build-static-site.py', 'analytics-consent.js',
                     'column-price.html', 'scripts/coupon_help_public_release.py',
                     'scripts/books_device_release_bundle.py'):
            self.assertNotIn(token, (ROOT / path).read_text(encoding='utf-8'))
        source = (ROOT / ('runtime-candidates/' + token + '.mjs')).read_text(encoding='utf-8')
        for forbidden in ('fetch(', 'sendBeacon(', 'gtag(', 'window.', 'document.',
                          'localStorage', 'setTimeout(', 'preventDefault(', 'stopPropagation('):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
