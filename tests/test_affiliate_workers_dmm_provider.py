from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateWorkersDmmProviderTests(unittest.TestCase):
    def test_provider_is_non_deployed_and_has_no_storage_or_logging(self):
        path = ROOT / "runtime-candidates" / "affiliate-workers-dmm-provider.mjs"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("functions", path.parts)
        self.assertFalse((ROOT / "functions").exists())
        for forbidden in ("console.", ".put(", ".write(", "INSERT", "export default"):
            self.assertNotIn(forbidden, source)
        self.assertIn('redirect: "error"', source)
        self.assertIn("MAX_RESPONSE_BYTES", source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_workers_dmm_provider_harness.mjs")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
