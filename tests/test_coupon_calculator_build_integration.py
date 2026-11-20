"""Opt-in build on isolated replicas only; no serving or production output."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest
from unittest import mock

from scripts.coupon_calculator_candidate_bundle import SOURCE_ASSETS
from scripts.coupon_calculator_release_bundle import OUTPUT_CSS, OUTPUT_JS
from scripts.article_navigation_release_bundle import ASSETS as NAVIGATION_ASSETS

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('calculator_build_integration', ROOT / 'scripts/build-static-site.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
PRODUCTION_FLAGS = ('--with-books-device', '--with-article-navigation')


class CalculatorBuildIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='calculator-build-')
        self.addCleanup(self.temp.cleanup)
        self.replica = Path(self.temp.name) / 'repo'
        self.replica.mkdir()
        names = (*builder.ALLOWLIST, 'preview/coupon-help.html', 'preview/books-device-review.html',
                 *SOURCE_ASSETS.values(), *(f'runtime-candidates/{name}' for name in NAVIGATION_ASSETS.values()))
        for name in names:
            target = self.replica / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def run_build(self, *flags):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return builder.main(['--repo-root', str(self.replica), *flags])

    def output(self):
        return {p.relative_to(self.replica/'dist').as_posix():p.read_bytes()
                for p in (self.replica/'dist').rglob('*') if p.is_file()}

    def test_default_then_opt_in_and_rollback_match_exactly(self):
        self.assertFalse(builder.parse_args([]).coupon_calculator_enabled)
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS),0)
        before = self.output()
        self.assertEqual(len(before),27)
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator'),0)
        enabled = self.output()
        self.assertEqual(len(enabled),29)
        self.assertEqual(set(enabled)-set(before),{OUTPUT_CSS,OUTPUT_JS})
        self.assertEqual({n for n in before if before[n]!=enabled[n]},{'coupon-help.html'})
        self.assertNotIn(b'noindex',enabled['coupon-help.html'])
        self.assertNotIn(b'<form',enabled['coupon-help.html'])
        self.assertNotIn(b'type="submit"',enabled['coupon-help.html'])
        self.assertNotIn(b"addEventListener('submit'",enabled[OUTPUT_JS])
        for flags in ((*PRODUCTION_FLAGS,'--without-coupon-calculator'),PRODUCTION_FLAGS):
            self.assertEqual(self.run_build(*flags),0)
            self.assertEqual(self.output(),before)
            self.assertFalse((self.replica/'dist/coupon-calculator').exists())

    def test_no_asset_dependency_or_output_when_disabled(self):
        for name in SOURCE_ASSETS.values():(self.replica/name).unlink()
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS),0)
        self.assertEqual(len(self.output()),27)

    def test_coupon_only_build_and_contradictory_flags(self):
        self.assertEqual(self.run_build('--with-coupon-calculator'),0)
        self.assertEqual(len(self.output()),24)
        before = self.output()
        for flags in (('--without-coupon-help','--with-coupon-calculator'),
                      ('--coupon-review-candidate','--with-coupon-calculator')):
            self.assertEqual(self.run_build(*flags),4)
            self.assertEqual(self.output(),before)
        with redirect_stderr(StringIO()),self.assertRaises(SystemExit):
            builder.parse_args(['--with-coupon-calculator','--without-coupon-calculator'])

    def test_dry_run_writes_nothing(self):
        before = {p.relative_to(self.replica).as_posix():p.read_bytes()
                  for p in self.replica.rglob('*') if p.is_file()}
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator','--dry-run'),0)
        after = {p.relative_to(self.replica).as_posix():p.read_bytes()
                 for p in self.replica.rglob('*') if p.is_file()}
        self.assertEqual(after,before)
        self.assertFalse((self.replica/'dist').exists())

    def test_missing_template_drift_and_forbidden_content_preserve_output(self):
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS),0)
        before = self.output()
        js = self.replica/SOURCE_ASSETS['js']
        original = js.read_bytes()
        js.unlink()
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator'),2)
        self.assertEqual(self.output(),before)
        js.write_bytes(b'const password = "test-only";')
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator'),4)
        self.assertEqual(self.output(),before)
        js.write_bytes(original)
        fragment=self.replica/SOURCE_ASSETS['fragment']
        fragment.write_bytes(fragment.read_bytes().replace(b'<form novalidate>',b'<form>'))
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator'),4)
        self.assertEqual(self.output(),before)

    def test_linked_asset_fails_without_replacing_output(self):
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS),0)
        before=self.output()
        asset=self.replica/SOURCE_ASSETS['js']
        original=Path.is_symlink
        with mock.patch.object(Path,'is_symlink',lambda p:p==asset or original(p)):
            self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator'),2)
        self.assertEqual(self.output(),before)

    def test_explicit_output_validation_and_stale_directory_guards(self):
        self.assertEqual(self.run_build(*PRODUCTION_FLAGS,'--with-coupon-calculator'),0)
        files=self.output()
        flags=dict(coupon_public=True,books_device=True,article_navigation=True,coupon_calculator=True)
        builder.validate_files(files,(),**flags)
        with self.assertRaises(builder.ValidationError):
            builder.validate_files(files,(),coupon_public=True,books_device=True,article_navigation=True)
        with self.assertRaises(builder.ValidationError):
            builder.validate_files(dict(files,**{'coupon-calculator/unexpected.js':b'bad'}),(),**flags)
        for value in (1,None,'true'):
            with self.assertRaises(builder.ValidationError):
                builder.expected_output_files(coupon_public=True,coupon_calculator=value)
        with self.assertRaises(builder.ValidationError):
            builder.expected_output_files(coupon_calculator=True)
        (self.replica/'dist/coupon-calculator/unexpected').mkdir()
        with self.assertRaises(builder.ValidationError):
            builder.validate_staging(self.replica/'dist',files,**flags)


if __name__=='__main__':unittest.main()
