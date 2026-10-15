"""Run the existing consent harness for the article route, entirely offline."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeviceConsentRuntimeTests(unittest.TestCase):
    def test_article_route_uses_existing_consent_boundaries(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not available')
        program = r'''
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const harness = fs.readFileSync('tests/analytics_consent_runtime_harness.js', 'utf8')
  .replaceAll('/items/item', '/books-device-check');
const extra = `
const articleConsent = scenario(null);
const acceptButton = articleConsent.bodyChildren[0].querySelector('.analytics-consent__accept');
acceptButton.trigger('click'); acceptButton.trigger('click');
assert(articleConsent.headChildren.length === 1, 'duplicate Google script');
const views = articleConsent.window.dataLayer.filter(x => x[0] === 'event' && x[1] === 'page_view');
assert(views.length === 1, 'duplicate page_view');
assert(views[0][2].page_location === 'https://datalabx.jp/books-device-check', 'wrong article route');
assert(views[0][2].page_referrer === '', 'referrer leaked');
`;
vm.runInNewContext(harness + extra, {
  require, __dirname: path.resolve('tests'), console, URLSearchParams
});
'''
        result = subprocess.run([node, '-e', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
