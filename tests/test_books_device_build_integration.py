from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.books_device_local_build import load_builder

ROOT = Path(__file__).resolve().parents[1]
ARTICLE = 'books-device-check.html'


class DeviceBuildIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='device-build-integration-')
        self.addCleanup(self.temp.cleanup)
        self.replica = Path(self.temp.name) / 'repo'
        self.replica.mkdir()
        self.builder = load_builder()
        for name in (*self.builder.ALLOWLIST, 'preview/coupon-help.html',
                     'preview/books-device-review.html'):
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

    def test_real_opt_in_and_rollback_same_output(self):
        self.assertEqual(self.run_build(), 0)
        baseline = self.outputs()
        self.assertEqual(len(baseline), 22)
        self.assertNotIn(ARTICLE, baseline)
        self.assertEqual(self.run_build('--with-books-device'), 0)
        release = self.outputs()
        self.assertEqual(len(release), 23)
        self.assertEqual(set(release) - set(baseline), {ARTICLE})
        self.assertEqual({n for n in baseline if baseline[n] != release[n]},
                         {'column-price.html', 'sitemap.xml'})
        self.assertNotIn(b'noindex', release[ARTICLE])
        self.assertEqual(release[ARTICLE].count(b'href="/column-price"'), 1)
        self.assertEqual(release['_headers'], baseline['_headers'])
        self.assertEqual(release['coupon-help.html'], baseline['coupon-help.html'])
        self.assertEqual(self.run_build('--without-books-device'), 0)
        self.assertEqual(self.outputs(), baseline)
        self.assertEqual(self.run_build('--with-books-device'), 0)
        self.assertEqual(self.run_build(), 0)
        self.assertEqual(self.outputs(), baseline)

    def test_opt_in_dry_run_creates_nothing(self):
        self.assertEqual(self.run_build('--with-books-device', '--dry-run'), 0)
        self.assertFalse((self.replica / 'dist').exists())

    def test_changed_draft_fails_without_replacing_existing_output(self):
        self.assertEqual(self.run_build(), 0)
        baseline = self.outputs()
        draft = self.replica / 'preview/books-device-review.html'
        draft.write_bytes(draft.read_bytes() + b'changed')
        self.assertEqual(self.run_build('--with-books-device'), 4)
        self.assertEqual(self.outputs(), baseline)
        self.assertEqual(self.run_build(), 0)

    def test_missing_draft_does_not_break_default(self):
        (self.replica / 'preview/books-device-review.html').unlink()
        self.assertEqual(self.run_build(), 0)
        self.assertEqual(self.run_build('--with-books-device'), 2)

    def test_coupon_rollback_and_review_modes(self):
        self.assertEqual(self.run_build('--with-books-device', '--without-coupon-help'), 0)
        self.assertIn(ARTICLE, self.outputs())
        self.assertNotIn('coupon-help.html', self.outputs())
        self.assertEqual(self.run_build('--with-books-device', '--coupon-review-candidate'), 4)

    def test_mutually_exclusive_flags_rejected(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            self.builder.parse_args(['--with-books-device', '--without-books-device'])
        self.assertEqual(error.exception.code, 2)

    def test_extra_article_requires_matching_validation_mode(self):
        files = self.builder.collect_sources(self.replica)
        files[ARTICLE] = b'passive fixture'
        with self.assertRaises(self.builder.ValidationError):
            self.builder.validate_files(files, ())
        self.builder.validate_files(files, (), books_device=True)
