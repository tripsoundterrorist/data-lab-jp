import ast
from pathlib import Path
import unittest
from xml.etree import ElementTree

from scripts.coupon_help_candidate_bundle import build_candidate_bundle, REQUIRED_INPUTS

ROOT = Path(__file__).resolve().parents[1]


class CandidateBundleTests(unittest.TestCase):
    def setUp(self):
        self.sources = {name: (ROOT / name).read_bytes() for name in REQUIRED_INPUTS}

    def test_bundle_is_separate_and_noindex(self):
        before = dict(self.sources)
        bundle = build_candidate_bundle(self.sources)
        self.assertEqual(set(bundle), {
            'coupon-help.html', 'column-price.html', 'sitemap.xml',
            'analytics-consent.js', 'analytics-consent.css', '_headers',
        })
        self.assertEqual(before, self.sources)
        self.assertIn(b'X-Robots-Tag: noindex, nofollow', bundle['_headers'])
        article = bundle['coupon-help.html'].decode('utf-8')
        self.assertIn('name="robots" content="noindex, nofollow"', article)
        self.assertIn('公開審査・公開承認は未完了', article)
        self.assertIn('src="/analytics-consent.js" defer', article)
        self.assertNotIn('<script src="https:', article)
        self.assertIn("script-src 'self' https://www.googletagmanager.com", article)
        self.assertIn("base-uri 'none'; form-action 'none'", article)
        self.assertEqual(bundle['analytics-consent.js'], before['analytics-consent.js'])
        self.assertEqual(bundle['analytics-consent.css'], before['analytics-consent.css'])

    def test_single_link_and_sitemap_entry(self):
        bundle = build_candidate_bundle(self.sources)
        self.assertEqual(bundle['column-price.html'].count(b'href="/coupon-help"'), 1)
        tree = ElementTree.fromstring(bundle['sitemap.xml'])
        locations = [node.text for node in tree.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertEqual(locations.count('https://datalabx.jp/coupon-help'), 1)

    def test_missing_extra_and_changed_inputs_rejected(self):
        for key, data in (
            ('column-price.html', b'<html></html>'),
            ('sitemap.xml', b'<urlset></urlset></urlset>'),
            ('preview/coupon-help.html', self.sources['preview/coupon-help.html'].replace(b'noindex, nofollow', b'index, follow')),
        ):
            bad = dict(self.sources); bad[key] = data
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_candidate_bundle(bad)
        for bad in ({}, {**self.sources, 'unexpected.txt': b'extra'}):
            with self.assertRaises(ValueError):
                build_candidate_bundle(bad)

    def test_normal_deployment_remains_excluded(self):
        tree = ast.parse((ROOT / 'scripts/build-static-site.py').read_text(encoding='utf-8'))
        values = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(
                      isinstance(t, ast.Name) and t.id == 'ALLOWLIST' for t in node.targets)]
        self.assertEqual(len(values), 1)
        self.assertNotIn('coupon-help.html', values[0])
        for name in ('sitemap.xml', 'column-price.html'):
            self.assertNotIn(b'/coupon-help', (ROOT / name).read_bytes())

    def test_duplicate_navigation_sitemap_and_csp_drift_rejected(self):
        mutations = (
            ('column-price.html', self.sources['column-price.html'] + b'<a href="/coupon-help">duplicate</a>'),
            ('sitemap.xml', self.sources['sitemap.xml'].replace(
                b'</urlset>', b'<url><loc>https://datalabx.jp/coupon-help</loc></url></urlset>')),
            ('preview/coupon-help.html', self.sources['preview/coupon-help.html'].replace(
                b"default-src 'none'", b"default-src 'self'")),
        )
        for name, content in mutations:
            bad = dict(self.sources)
            bad[name] = content
            before = dict(bad)
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_candidate_bundle(bad)
            self.assertEqual(bad, before)

    def test_repeat_build_and_discard_leave_source_rollback_baseline_intact(self):
        before = dict(self.sources)
        first = build_candidate_bundle(self.sources)
        self.assertEqual(first, build_candidate_bundle(self.sources))
        first.clear()  # Discarding a local artifact must not alter source bytes.
        self.assertEqual(self.sources, before)
        for name, content in before.items():
            self.assertEqual((ROOT / name).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
