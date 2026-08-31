import importlib.util
import io
from pathlib import Path
import unittest
from unittest import mock
from contextlib import redirect_stderr


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "run_test_tier.py"
SPEC = importlib.util.spec_from_file_location("run_test_tier", MODULE_PATH)
run_test_tier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(run_test_tier)


class TestTestTiersContract(unittest.TestCase):
    def test_tiers_are_fixed(self):
        self.assertEqual(run_test_tier.TIERS, ("fast", "regression", "full"))

    def test_fast_manifest_is_explicit_unique_and_existing(self):
        modules = run_test_tier._validate_fast_manifest()
        self.assertEqual(len(modules), len(set(modules)))
        self.assertTrue(modules)
        for module in modules:
            self.assertTrue((ROOT / "tests" / f"{module}.py").is_file())

    def test_fast_suite_is_smaller_than_regression(self):
        fast = run_test_tier.build_suite("fast").countTestCases()
        regression = run_test_tier.build_suite("regression").countTestCases()
        self.assertGreater(fast, 0)
        self.assertLess(fast, regression)

    def test_unknown_tier_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_TEST_TIER"):
            run_test_tier.build_suite("smoke")

    def test_full_stops_if_script_compilation_fails(self):
        with mock.patch.object(run_test_tier.compileall, "compile_dir", return_value=False):
            self.assertEqual(run_test_tier.run("full"), 1)

    def test_full_compiles_before_loading_suite(self):
        with (
            mock.patch.object(run_test_tier.compileall, "compile_dir", return_value=True) as compile_dir,
            mock.patch.object(run_test_tier, "build_suite", return_value=unittest.TestSuite()),
        ):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(run_test_tier.run("full"), 0)
        self.assertEqual(compile_dir.call_count, 2)


if __name__ == "__main__":
    unittest.main()
