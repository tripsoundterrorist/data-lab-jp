from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.books_device_local_build import check_output, collect_rehearsal, main, ROOT
from scripts.books_device_release_bundle import ARTICLE


class LocalBuildTests(unittest.TestCase):
    def test_real_baseline_and_release_differ_only_in_three_files(self):
        rollback = collect_rehearsal('rollback')
        release = collect_rehearsal('release')
        self.assertEqual(len(rollback), 22)
        self.assertEqual(len(release), 23)
        self.assertEqual(set(release) - set(rollback), {ARTICLE})
        self.assertEqual({name for name in rollback if release[name] != rollback[name]},
                         {'column-price.html', 'sitemap.xml'})
        self.assertIn('coupon-help.html', rollback)
        self.assertEqual(release['_headers'], rollback['_headers'])

    def test_real_local_outputs_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='books-device-local-') as tmp:
            root = Path(tmp).resolve()
            release, rollback = root / 'release', root / 'rollback'
            self.assertEqual(main(['--mode', 'release', '--output', str(release)]), 0)
            self.assertEqual(main(['--mode', 'rollback', '--output', str(rollback)]), 0)
            self.assertTrue((release / ARTICLE).is_file())
            self.assertFalse((rollback / ARTICLE).exists())
            for name, data in collect_rehearsal('rollback').items():
                self.assertEqual((rollback / name).read_bytes(), data)
            before = (release / ARTICLE).read_bytes()
            self.assertEqual(main(['--mode', 'rollback', '--output', str(release)]), 1)
            self.assertEqual((release / ARTICLE).read_bytes(), before)

    def test_dry_run_does_not_create_output(self):
        with tempfile.TemporaryDirectory(prefix='books-device-local-') as tmp:
            output = Path(tmp).resolve() / 'dry'
            self.assertEqual(main(['--mode', 'release', '--output', str(output), '--dry-run']), 0)
            self.assertFalse(output.exists())

    def test_unsafe_paths_fail_before_collecting(self):
        for output in (Path('relative'), ROOT / 'dist', Path(tempfile.gettempdir()).resolve()):
            with patch('scripts.books_device_local_build.collect_rehearsal') as collect:
                self.assertEqual(main(['--mode', 'release', '--output', str(output)]), 1)
                collect.assert_not_called()

    def test_symlink_path_rejected(self):
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaisesRegex(ValueError, 'SYMLINK'):
                check_output(Path(tempfile.gettempdir()).resolve() / 'candidate')

    def test_unknown_mode_rejected(self):
        with self.assertRaisesRegex(ValueError, 'UNKNOWN'):
            collect_rehearsal('publish')
