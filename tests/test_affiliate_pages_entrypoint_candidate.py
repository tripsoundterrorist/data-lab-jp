from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliatePagesEntrypointCandidateTests(unittest.TestCase):
    def test_entrypoint_is_not_auto_deployed(self):
        path = ROOT / "runtime-candidates" / "affiliate-pages-entrypoint-candidate.mjs"
        source = path.read_text(encoding="utf-8")
        self.assertFalse((ROOT / "functions").exists())
        self.assertNotIn("functions", path.parts)
        self.assertNotIn("export async function onRequest", source)
        self.assertNotIn("console.", source)
        self.assertNotIn("caches.", source)
        self.assertIn('"Cache-Control": "no-store, max-age=0"', source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_pages_entrypoint_candidate_harness.mjs")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
