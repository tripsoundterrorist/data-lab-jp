"""Explicit local opt-in never changes the default production artifact."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_revenue_mvp_static_build import build


class CouponBuildIntegrationTests(unittest.TestCase):
    def test_review_then_default_rollback_keeps_source_and_dist_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            root.mkdir()
            names = list(build.ALLOWLIST) + ['preview/coupon-help.html']
            before = {name: (ROOT / name).read_bytes() for name in names}
            for name, data in before.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            def run(*args):
                return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/build-static-site.py'),
                                       '--repo-root', str(root), *args], capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            baseline = {p.relative_to(root / 'dist').as_posix(): p.read_bytes()
                        for p in (root / 'dist').rglob('*') if p.is_file()}
            output = Path(temp) / 'review'
            dry = run('--coupon-review-candidate', '--output', str(output), '--dry-run')
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn('Mode: coupon-review-dry-run', dry.stdout)
            self.assertIn('publication not authorized', dry.stdout)
            self.assertFalse(output.exists())
            process = run('--coupon-review-candidate', '--output', str(output))
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn('Mode: coupon-review-generated', process.stdout)
            self.assertTrue((output / 'coupon-help.html').is_file())
            self.assertIn(b'noindex, nofollow', (output / 'coupon-help.html').read_bytes())
            self.assertIn(b'X-Robots-Tag: noindex, nofollow', (output / '_headers').read_bytes())
            self.assertTrue((output / '_headers').read_bytes().startswith(before['_headers']))
            self.assertIn(b'/coupon-help', (output / 'column-price.html').read_bytes())
            self.assertIn(b'/coupon-help', (output / 'sitemap.xml').read_bytes())
            self.assertEqual(run().returncode, 0)
            after = {p.relative_to(root / 'dist').as_posix(): p.read_bytes()
                     for p in (root / 'dist').rglob('*') if p.is_file()}
            self.assertEqual(after, baseline)
            for name, data in before.items():
                self.assertEqual((root / name).read_bytes(), data)
            self.assertNotEqual(run('--coupon-review-candidate').returncode, 0)
            self.assertNotEqual(run('--coupon-review-candidate', '--output', str(output)).returncode, 0)
            self.assertNotEqual(run('--coupon-review-candidate', '--output', str(root / 'dist')).returncode, 0)
            self.assertNotEqual(run('--coupon-review-candidate', '--output', 'relative-review').returncode, 0)
            self.assertNotEqual(run('--coupon-review-candidate', '--output', tempfile.gettempdir()).returncode, 0)


if __name__ == '__main__':
    unittest.main()
