from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class AffiliateD1RuntimeAdapterTests(unittest.TestCase):
    def test_candidate_is_non_deployed_and_read_only(self):
        candidate = ROOT / "runtime-candidates" / "affiliate-d1-runtime-adapter.mjs"
        source = candidate.read_text(encoding="utf-8")
        self.assertTrue(candidate.is_file())
        self.assertNotIn("functions", candidate.parts)
        self.assertFalse((ROOT / "functions").exists())
        self.assertNotIn("onRequest", source)
        self.assertNotIn("export default", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("affiliate_enabled = 1", source)

    def test_candidate_queries_only_eligible_view(self):
        source = (ROOT / "runtime-candidates" / "affiliate-d1-runtime-adapter.mjs").read_text(encoding="utf-8")
        self.assertIn("env?.AFFILIATE_ITEM_LOOKUP", source)
        self.assertIn("FROM affiliate_runtime_eligible_lookup", source)
        self.assertNotIn("FROM affiliate_item_lookup", source)
        self.assertIn("WHERE public_id = ? LIMIT 2", source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        result = subprocess.run([node, str(ROOT / "tests" / "affiliate_d1_runtime_adapter_harness.mjs")],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
