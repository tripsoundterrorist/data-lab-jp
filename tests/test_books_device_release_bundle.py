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
        for forbidden in ('noindex', '未公開', 'ローカルレビュー', '/go/'):
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

    def test_public_build_requires_explicit_opt_in(self):
        from scripts.books_device_local_build import load_builder
        builder = load_builder()
        self.assertFalse(builder.parse_args([]).books_device_enabled)
        self.assertFalse(builder.parse_args(['--without-books-device']).books_device_enabled)
        self.assertTrue(builder.parse_args(['--with-books-device']).books_device_enabled)

    def test_only_existing_local_consent_bootstrap_added(self):
        from html.parser import HTMLParser
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__()
                self.scripts = []
                self.styles = []
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == 'script':
                    self.scripts.append(values)
                if tag == 'link' and values.get('rel') == 'stylesheet':
                    self.styles.append(values.get('href'))
        bundle = build_release_bundle(self.baseline, self.source, enabled=True)
        article = bundle[ARTICLE].decode('utf-8')
        parser = Tags()
        parser.feed(article)
        self.assertEqual(parser.scripts, [{'src': '/analytics-consent.js', 'defer': None}])
        self.assertEqual(parser.styles, ['/analytics-consent.css'])
        for asset in ('analytics-consent.js', 'analytics-consent.css', '_headers'):
            self.assertEqual(bundle[asset], self.baseline[asset])
        self.assertIn("script-src 'self' https://www.googletagmanager.com", article)
        self.assertIn('href="/privacy"', article)
        self.assertNotIn('gtag(', article)
        self.assertNotIn('G-ZPBQJ6137L', article)

    def test_missing_consent_assets_fail_closed_when_enabled(self):
        for asset in ('analytics-consent.js', 'analytics-consent.css'):
            baseline = dict(self.baseline)
            del baseline[asset]
            with self.assertRaisesRegex(ValueError, 'CONSENT_ASSETS_MISSING'):
                build_release_bundle(baseline, self.source, enabled=True)
            self.assertEqual(build_release_bundle(baseline, b''), baseline)

    def test_one_related_price_link_between_checklist_and_footer(self):
        article = build_release_bundle(self.baseline, self.source, enabled=True)[ARTICLE].decode('utf-8')
        self.assertEqual(article.count('href="/column-price"'), 1)
        self.assertIn('FANZA動画の価格・視聴条件の確認ポイント</a>', article)
        self.assertLess(article.index('<section id="check"'), article.index('<p class="related">'))
        self.assertLess(article.index('<p class="related">'), article.index('<footer>'))
        self.assertNotIn('href="/items/"', article)
        self.assertNotIn('href="/go/', article)

    def test_related_link_does_not_change_source_or_disabled_output(self):
        before = dict(self.baseline)
        first = build_release_bundle(self.baseline, self.source, enabled=True)
        self.assertEqual(first, build_release_bundle(self.baseline, self.source, enabled=True))
        self.assertEqual(self.baseline, before)
        self.assertEqual((ROOT / 'preview/books-device-review.html').read_bytes(), self.source)
        self.assertEqual(build_release_bundle(self.baseline, self.source), before)
