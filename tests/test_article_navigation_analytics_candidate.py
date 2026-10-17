"""Entirely offline candidate tests. No live pages, analytics or settings."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'runtime-candidates/article-navigation-analytics-candidate.mjs'


class ArticleNavigationCandidateTests(unittest.TestCase):
    def test_offline_runtime_boundaries(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not available')
        program = r'''
import assert from 'node:assert/strict';
import { createArticleNavigationObserver as create } from './runtime-candidates/article-navigation-analytics-candidate.mjs';
const routes = [
  ['/coupon-help', '/column-price', 'coupon_to_price'],
  ['/books-device-check', '/column-price', 'device_to_price'],
  ['/column-price', '/items/', 'price_to_items'],
];
let consent = null;
const recorded = [];
const observe = create(() => consent, payload => { recorded.push(payload); return true; });
const valid = {from: '/coupon-help', to: '/column-price'};
for (const choice of [null, undefined, 'denied', '', 'GRANTED', true]) {
  consent = choice;
  assert.equal(observe(valid), false);
}
assert.equal(recorded.length, 0);
consent = 'granted';
assert.equal(recorded.length, 0); // No delayed replay after grant.
for (const [from, to, label] of routes) {
  const input = Object.freeze({from, to});
  assert.equal(observe(input), true);
  assert.deepEqual(recorded.at(-1), {
    event_name: 'article_navigation_click', navigation_route: label,
  });
  assert(Object.isFrozen(recorded.at(-1)));
}
consent = 'denied'; // Withdrawal is checked for every observation.
assert.equal(observe(valid), false);
assert.equal(recorded.length, 3);
consent = 'granted';
for (const input of [
  null, undefined, [], '', {},
  {from: '/coupon-help'}, {to: '/column-price'},
  {...valid, user_id: 'private'}, {...valid, public_id: 'private'},
  {...valid, query: 'private'}, {...valid, [Symbol('extra')]: true},
  {from: '/coupon-help?secret=value', to: '/column-price'},
  {from: '/coupon-help', to: '/column-price#fragment'},
  {from: '/coupon-help', to: 'https://datalabx.jp/column-price'},
  {from: '/column-price', to: '/go/private'},
  {from: '/items/', to: '/column-price'},
]) assert.equal(observe(input), false);
assert.equal(recorded.length, 3);
assert.equal(create(undefined, () => true)(valid), false);
assert.equal(create(() => 'granted', undefined)(valid), false);
assert.equal(create(() => { throw Error('storage unavailable'); }, () => true)(valid), false);
assert.equal(create(() => 'granted', () => { throw Error('recorder failed'); })(valid), false);
assert.equal(create(() => 'granted', () => undefined)(valid), false);
const hostile = new Proxy({}, {ownKeys() { throw Error('invalid input'); }});
assert.equal(observe(hostile), false);
assert.deepEqual(Object.keys(recorded[0]).sort(), ['event_name', 'navigation_route']);
'''
        result = subprocess.run(
            [node, '--input-type=module', '-e', program], cwd=ROOT,
            capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_candidate_has_no_active_transport_or_page_integration(self):
        source = (ROOT / MODULE).read_text(encoding='utf-8')
        for token in ('fetch(', 'sendBeacon(', 'gtag(', 'window.', 'document.',
                      'localStorage', 'setTimeout(', 'addEventListener('):
            self.assertNotIn(token, source)
        builder = (ROOT / 'scripts/build-static-site.py').read_text(encoding='utf-8')
        self.assertNotIn('article-navigation-analytics-candidate', builder)
        for path in ('analytics-consent.js', 'column-price.html',
                     'scripts/coupon_help_public_release.py',
                     'scripts/books_device_release_bundle.py'):
            self.assertNotIn('article-navigation-analytics-candidate',
                             (ROOT / path).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
