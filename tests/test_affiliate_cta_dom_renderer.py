from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateCtaDomRendererTests(unittest.TestCase):
    def test_renderer_is_isolated_and_accepts_no_external_url(self):
        path = ROOT / "runtime-candidates" / "affiliate-cta-dom-renderer.mjs"
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("items.js", path.parts)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("console.", source)
        self.assertIn("`/go/${publicId}`", source)
        self.assertIn("wrapper.append(disclosure, link)", source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_cta_dom_renderer_harness.mjs")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
