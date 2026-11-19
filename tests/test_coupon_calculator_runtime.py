"""Execute candidate UI in an inert DOM; no browser or network acquisition."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CouponCalculatorRuntimeTests(unittest.TestCase):
    def test_arithmetic_boundaries_and_dom_flow(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js unavailable; runtime verification incomplete')
        result = subprocess.run([node, str(ROOT / 'tests/coupon_calculator_runtime_harness.cjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS', result.stdout)


if __name__ == '__main__':unittest.main()
