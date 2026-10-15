from pathlib import Path
import unittest
from scripts.books_device_release_bundle import build_release_bundle, ARTICLE, ROUTE

ROOT = Path(__file__).resolve().parents[1]


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'preview/books-device-review.html').read_bytes()
        self.baseline = {name: (ROOT / name).read_bytes() for name in
                         ('column-price.html', 'sitemap.xml', '_headers', 'robots.txt',
                          'analytics-consent.js', 'analytics-consent.css')}

    def test_default_is_exact_baseline(self):
        self.assertEqual(build_release_bundle(self.baseline, b''), self.baseline)

    def test_enabled_changes_only_three_outputs(self):
        before = dict(self.baseline)
        result = build_release_bundle(self.baseline, self.source, enabled=True)
        self.assertEqual(set(result) - set(before), {ARTICLE})
        self.assertEqual({n for n in before if result[n] != before[n]},
                         {'column-price.html', 'sitemap.xml'})
        self.assertEqual(self.baseline, before)
        article = result[ARTICLE].decode('utf-8')
        for forbidden in ('noindex', '未公開', 'ローカルレビュー', '<script', '/go/'):
            self.assertNotIn(forbidden, article)
        self.assertEqual(result['column-price.html'].count(f'href="{ROUTE}"'.encode()), 1)
        self.assertEqual(result['sitemap.xml'].count(f'https://datalabx.jp{ROUTE}'.encode()), 1)

    def test_rollback_rebuild_restores_all_three(self):
        release = build_release_bundle(self.baseline, self.source, enabled=True)
        rollback = build_release_bundle(self.baseline, self.source, enabled=False)
        self.assertIn(ARTICLE, release)
        self.assertNotIn(ARTICLE, rollback)
        self.assertEqual(rollback, self.baseline)

    def test_generated_baseline_rejected(self):
        release = build_release_bundle(self.baseline, self.source, enabled=True)
        for enabled in (True, False):
            with self.assertRaisesRegex(ValueError, 'PRISTINE_BASELINE_REQUIRED'):
                build_release_bundle(release, self.source, enabled=enabled)

    def test_bad_inputs_fail_closed_without_mutation(self):
        before = dict(self.baseline)
        with self.assertRaises(ValueError):
            build_release_bundle(self.baseline, self.source + b'changed', enabled=True)
        with self.assertRaises(ValueError):
            build_release_bundle({}, self.source, enabled=True)
        for value in ('true', 1, None):
            with self.assertRaises(ValueError):
                build_release_bundle(self.baseline, self.source, enabled=value)
        for name, old in (('column-price.html', b'        <a class="back" href="/">'),
                          ('sitemap.xml', b'</urlset>')):
            for count in (0, 2):
                bad = dict(self.baseline)
                bad[name] = bad[name].replace(old, old * count)
                with self.assertRaises(ValueError):
                    build_release_bundle(bad, self.source, enabled=True)
        self.assertEqual(self.baseline, before)

    def test_no_deployment_connection(self):
        build = (ROOT / 'scripts/build-static-site.py').read_text(encoding='utf-8')
        self.assertNotIn('books_device_release_bundle', build)
