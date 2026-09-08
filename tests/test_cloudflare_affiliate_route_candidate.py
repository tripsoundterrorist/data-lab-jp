from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CloudflareAffiliateRouteCandidateTests(unittest.TestCase):
    def require_node(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        return node

    def test_candidate_is_not_in_cloudflare_functions_directory(self):
        candidate = ROOT / "runtime-candidates" / "cloudflare-affiliate-route.mjs"
        self.assertTrue(candidate.is_file())
        self.assertNotIn("functions", candidate.parts)
        self.assertFalse((ROOT / "functions").exists())

    def test_candidate_has_no_handler_export_and_binding_remains_fail_closed(self):
        source = (
            ROOT / "runtime-candidates" / "cloudflare-affiliate-route.mjs"
        ).read_text(encoding="utf-8")
        self.assertNotIn("onRequest", source)
        self.assertNotIn("export default", source)
        self.assertFalse((ROOT / "wrangler.jsonc").exists())

        wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn('binding = "AFFILIATE_ITEM_LOOKUP"', wrangler)
        self.assertIn('database_name = "data-lab-affiliate-lookup"', wrangler)
        self.assertNotIn("/go/:public_id", wrangler)
        self.assertNotIn("affiliate_enabled = true", wrangler)

    def test_candidate_runtime_boundary_in_node(self):
        result = subprocess.run(
            [
                self.require_node(),
                str(ROOT / "tests" / "cloudflare_affiliate_route_candidate_harness.mjs"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

