"""Ordinary build opt-in/rollback on isolated replicas only; no network or serving."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.article_navigation_release_bundle import ASSETS, PAGES, CONSENT_NEW
from scripts.article_navigation_local_build import collect_local_bundle
from scripts.books_device_local_build import ROOT, load_builder


class NavigationBuildIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='navigation-integration-')
        self.addCleanup(self.temp.cleanup)
        self.replica = Path(self.temp.name) / 'repo'
        self.replica.mkdir()
        self.builder = load_builder()
        for name in (*self.builder.ALLOWLIST, 'preview/coupon-help.html',
                     'preview/books-device-review.html',
                     *(f'runtime-candidates/{name}' for name in ASSETS.values())):
            target = self.replica / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def run_build(self, *flags):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return self.builder.main(['--repo-root', str(self.replica), *flags])

    def outputs(self):
        dist = self.replica / 'dist'
        return {p.relative_to(dist).as_posix(): p.read_bytes()
                for p in dist.rglob('*') if p.is_file()}

    def test_default_on_default_off_and_explicit_rollback_are_exact(self):
        self.assertFalse(self.builder.parse_args([]).article_navigation_enabled)
        self.assertEqual(self.run_build('--with-books-device'), 0)
        baseline = self.outputs()
        self.assertEqual(baseline, collect_local_bundle(enabled=False))
        self.assertEqual(len(baseline), 23)
        self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation'), 0)
        enabled = self.outputs()
        self.assertEqual(enabled, collect_local_bundle(enabled=True))
        self.assertEqual(set(enabled) - set(baseline), set(ASSETS))
        self.assertEqual({n for n in baseline if enabled[n] != baseline[n]},
                         set(PAGES) | {'analytics-consent.js'})
        self.assertIn(CONSENT_NEW.encode(), enabled['analytics-consent.js'])
        for name in PAGES:
            self.assertEqual(enabled[name].count(b'/article-navigation/bootstrap.mjs'), 1)
        self.assertEqual(enabled['_headers'], baseline['_headers'])
        self.assertEqual(enabled['sitemap.xml'], baseline['sitemap.xml'])
        self.assertEqual(enabled['items/discovery.js'], baseline['items/discovery.js'])
        self.assertEqual(self.run_build('--with-books-device'), 0)
        self.assertEqual(self.outputs(), baseline)
        self.assertFalse((self.replica / 'dist/article-navigation').exists())
        self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation'), 0)
        self.assertEqual(self.run_build('--with-books-device', '--without-article-navigation'), 0)
        self.assertEqual(self.outputs(), baseline)

    def test_opt_in_requires_all_three_articles_and_rejects_conflicting_flags(self):
        for flags in (('--with-article-navigation',),
                      ('--with-books-device', '--without-coupon-help', '--with-article-navigation'),
                      ('--coupon-review-candidate', '--with-article-navigation')):
            with self.subTest(flags=flags):
                self.assertEqual(self.run_build(*flags), 4)
                self.assertFalse((self.replica / 'dist').exists())
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            self.builder.parse_args(['--with-article-navigation', '--without-article-navigation'])

    def test_opt_in_dry_run_writes_nothing(self):
        before = {p.relative_to(self.replica).as_posix(): p.read_bytes()
                  for p in self.replica.rglob('*') if p.is_file()}
        self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation', '--dry-run'), 0)
        self.assertEqual(before, {p.relative_to(self.replica).as_posix(): p.read_bytes()
                                 for p in self.replica.rglob('*') if p.is_file()})

    def test_missing_source_does_not_replace_existing_output(self):
        self.assertEqual(self.run_build('--with-books-device'), 0)
        baseline = self.outputs()
        (self.replica / 'runtime-candidates/article-navigation-bootstrap-candidate.mjs').unlink()
        self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation'), 2)
        self.assertEqual(self.outputs(), baseline)
        self.assertEqual(self.run_build('--with-books-device'), 0)
        self.assertEqual(self.outputs(), baseline)

    def test_forbidden_asset_content_and_symlinks_fail_closed(self):
        self.assertEqual(self.run_build('--with-books-device'), 0)
        baseline = self.outputs()
        asset = self.replica / 'runtime-candidates/article-navigation-bootstrap-candidate.mjs'
        original = asset.read_bytes()
        asset.write_bytes(b'const password = "fixture";')
        self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation'), 4)
        self.assertEqual(self.outputs(), baseline)
        asset.write_bytes(original)
        real_check = Path.is_symlink
        with mock.patch.object(Path, 'is_symlink',
                               lambda p: p == asset or real_check(p)):
            self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation'), 2)
        self.assertEqual(self.outputs(), baseline)

    def test_output_allowlist_and_staging_reject_extra_or_disabled_assets(self):
        self.assertEqual(self.run_build('--with-books-device', '--with-article-navigation'), 0)
        files = self.outputs()
        with self.assertRaises(self.builder.ValidationError):
            self.builder.validate_files(files, (), coupon_public=True, books_device=True)
        self.builder.validate_files(files, (), coupon_public=True, books_device=True,
                                    article_navigation=True)
        bad = dict(files, **{'article-navigation/unexpected.mjs': b'extra'})
        with self.assertRaises(self.builder.ValidationError):
            self.builder.validate_files(bad, (), coupon_public=True, books_device=True,
                                        article_navigation=True)
        extra = self.replica / 'dist/unexpected'
        extra.mkdir()
        with self.assertRaises(self.builder.ValidationError):
            self.builder.validate_staging(self.replica / 'dist', files, coupon_public=True,
                                          books_device=True, article_navigation=True)


if __name__ == '__main__':
    unittest.main()
