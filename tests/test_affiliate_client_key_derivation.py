from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateClientKeyDerivationTests(unittest.TestCase):
    def test_candidate_is_isolated_and_has_no_storage_or_logging(self):
        path = ROOT / "runtime-candidates" / "affiliate-client-key-derivation.mjs"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("functions", path.parts)
        self.assertFalse((ROOT / "functions").exists())
        for forbidden in ("console.", ".put(", ".write(", "INSERT", "fetch(", "export default"):
            self.assertNotIn(forbidden, source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_client_key_derivation_harness.mjs")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
