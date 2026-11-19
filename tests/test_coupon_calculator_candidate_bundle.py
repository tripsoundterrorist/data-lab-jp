"""Offline composition only; no production build or transport."""
from pathlib import Path
import re
import unittest
from unittest import mock

from scripts.coupon_help_candidate_bundle import REQUIRED_INPUTS, build_candidate_bundle as coupon_review
from scripts.coupon_help_public_release import build_public_release
from scripts.books_device_release_bundle import build_release_bundle as device_release
from scripts.article_navigation_release_bundle import build_navigation_bundle, collect_assets as navigation_assets
from scripts import coupon_calculator_candidate_bundle as calc

ROOT = Path(__file__).resolve().parents[1]


class CouponCalculatorBundleTests(unittest.TestCase):
    def setUp(self):
        self.sources = {name: (ROOT / name).read_bytes() for name in REQUIRED_INPUTS}
        self.baseline = build_public_release(self.sources)
        self.baseline['_headers'] = (ROOT / '_headers').read_bytes()
        self.assets = calc.collect_assets(ROOT)

    def test_disabled_exact_identity_even_without_assets(self):
        self.assertEqual(calc.build_candidate_bundle(self.baseline, {}), self.baseline)
        self.assertEqual(calc.build_candidate_bundle(self.baseline, {}, enabled=False), self.baseline)

    def test_enabled_only_changes_article_and_review_headers(self):
        before = dict(self.baseline)
        result = calc.build_candidate_bundle(self.baseline, self.assets, enabled=True)
        self.assertEqual(self.baseline, before)
        self.assertEqual(set(result) - set(before), {calc.OUTPUT_CSS, calc.OUTPUT_JS})
        self.assertEqual({name for name in before if before[name] != result[name]},
                         {'coupon-help.html', '_headers'})
        self.assertEqual(result['_headers'], before['_headers'] + calc.HEADERS)
        html = result['coupon-help.html'].decode('utf-8')
        self.assertEqual(html.count(calc.TAGS), 1)
        self.assertEqual(html.count(calc.NOINDEX), 1)
        self.assertEqual(html.count('<h1>'), 1)
        parser = calc._Markup(); parser.feed(html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertTrue(set(parser.refs) <= set(parser.ids))

    def test_original_article_restores_exactly_by_removing_additions(self):
        result = calc.build_candidate_bundle(self.baseline, self.assets, enabled=True)
        article = result['coupon-help.html'].decode('utf-8')
        article = article.replace(self.assets['fragment'].decode('utf-8'), '', 1)
        article = article.replace(calc.TAGS, '', 1).replace(calc.NOINDEX, '', 1)
        self.assertEqual(article.encode('utf-8'), self.baseline['coupon-help.html'])

    def test_composes_with_review_article_without_duplicate_noindex(self):
        baseline = coupon_review(self.sources)
        result = calc.build_candidate_bundle(baseline, self.assets, enabled=True)
        self.assertEqual(result['coupon-help.html'].count(b'name="robots"'), 1)
        self.assertIn(b'noindex, nofollow', result['coupon-help.html'])

    def test_composes_with_device_and_navigation_keeps_all_analytics_bytes(self):
        baseline = device_release(self.baseline, (ROOT / 'preview/books-device-review.html').read_bytes(), enabled=True)
        baseline = build_navigation_bundle(baseline, navigation_assets(ROOT), enabled=True)
        result = calc.build_candidate_bundle(baseline, self.assets, enabled=True)
        for name in baseline:
            if name not in {'coupon-help.html', '_headers'}:
                self.assertEqual(result[name], baseline[name], name)
        self.assertIn(b'/article-navigation/bootstrap.mjs', result['coupon-help.html'])
        self.assertIn(b'/analytics-consent.js', result['coupon-help.html'])
        self.assertEqual(result['coupon-help.html'].count(b'/article-navigation/bootstrap.mjs'), 1)
        self.assertEqual(re.findall(rb'href="/column-price"', result['coupon-help.html']),
                         re.findall(rb'href="/column-price"', baseline['coupon-help.html']))

    def test_missing_extra_and_nonbyte_inputs_rejected(self):
        for assets in ({}, dict(self.assets, extra=b'bad'), {**self.assets, 'js':'bad'}):
            with self.subTest(assets=list(assets)), self.assertRaises(ValueError):
                calc.build_candidate_bundle(self.baseline, assets, enabled=True)
        with self.assertRaises(ValueError):
            calc.build_candidate_bundle({}, self.assets, enabled=True)

    def test_nonboolean_rejected(self):
        for value in [0, 1, None, 'true']:
            with self.assertRaises(ValueError):
                calc.build_candidate_bundle(self.baseline, self.assets, enabled=value)

    def test_anchor_drift_and_duplicate_integration_fail_closed(self):
        for article in [self.baseline['coupon-help.html'].replace(calc.ANCHOR.encode(), b''),
                        self.baseline['coupon-help.html'] + calc.ANCHOR.encode()]:
            baseline = dict(self.baseline, **{'coupon-help.html':article})
            with self.assertRaises(ValueError):calc.build_candidate_bundle(baseline, self.assets, enabled=True)
        result = calc.build_candidate_bundle(self.baseline, self.assets, enabled=True)
        with self.assertRaises(ValueError):calc.build_candidate_bundle(result, self.assets, enabled=True)

    def test_bad_fragment_and_id_collisions_fail_closed(self):
        for fragment in [self.assets['fragment'] + b'<script>bad</script>',
                         self.assets['fragment'] + b'<input id="missing">',
                         self.assets['fragment'] + b'<label for="missing-id">bad</label>',
                         self.assets['fragment'] + b'<a href="https://example.invalid">bad</a>']:
            with self.assertRaises(ValueError):
                calc.build_candidate_bundle(self.baseline, {**self.assets, 'fragment':fragment}, enabled=True)

    def test_existing_robots_index_is_not_silently_replaced(self):
        baseline = dict(self.baseline, **{'coupon-help.html':self.baseline['coupon-help.html'].replace(
            b'</head>', b'<meta name="robots" content="index">\n</head>')})
        with self.assertRaises(ValueError):calc.build_candidate_bundle(baseline, self.assets, enabled=True)

    def test_missing_or_linked_asset_rejected(self):
        with self.assertRaises((OSError, ValueError)):
            calc.collect_assets(ROOT / 'not-a-source-root')
        real_check = Path.is_symlink
        linked = ROOT / calc.SOURCE_ASSETS['js']
        with mock.patch.object(Path, 'is_symlink', lambda p: p == linked or real_check(p)):
            with self.assertRaisesRegex(ValueError, 'LINKED_SOURCE'):calc.collect_assets(ROOT)

    def test_no_public_hook_and_network_storage_or_tracking(self):
        for name in ('scripts/build-static-site.py', 'scripts/coupon_help_public_release.py',
                     'preview/coupon-help.html', 'analytics-consent.js'):
            self.assertNotIn('coupon-calculator', (ROOT / name).read_text(encoding='utf-8'))
        js = self.assets['js'].decode('utf-8')
        for forbidden in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage', 'sessionStorage',
                          'gtag(', 'globalThis.', 'document.cookie', 'innerHTML', 'eval('):
            self.assertNotIn(forbidden, js)
        self.assertNotIn(b'<script', self.assets['fragment'])


if __name__ == '__main__':unittest.main()
