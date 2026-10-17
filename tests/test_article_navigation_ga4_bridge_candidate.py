"""Mock GA4 invocation and composition only; no live transport or settings."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ArticleNavigationBridgeTests(unittest.TestCase):
    def test_mock_payload_consent_and_dom_composition(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not available')
        result = subprocess.run(
            [node, str(ROOT / 'tests/article_navigation_ga4_bridge_harness.mjs')],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bridge_is_not_integrated_or_network_capable(self):
        token = 'article-navigation-ga4-bridge-candidate'
        for path in ('scripts/build-static-site.py', 'analytics-consent.js',
                     'column-price.html', 'scripts/coupon_help_public_release.py',
                     'scripts/books_device_release_bundle.py', 'items/discovery.js'):
            self.assertNotIn(token, (ROOT / path).read_text(encoding='utf-8'))
        source = (ROOT / ('runtime-candidates/' + token + '.mjs')).read_text(encoding='utf-8')
        for forbidden in ('fetch(', 'sendBeacon(', 'gtag(', 'window.', 'document.',
                          'localStorage', 'setTimeout(', 'config",', 'config\",'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
