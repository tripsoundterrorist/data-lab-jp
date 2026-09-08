from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateRateLimitAdapterTests(unittest.TestCase):
    def test_candidate_is_non_deployed_and_has_no_side_effect_capabilities(self):
        candidate = ROOT / "runtime-candidates" / "affiliate-rate-limit-adapter.mjs"
        source = candidate.read_text(encoding="utf-8")
        self.assertTrue(candidate.is_file())
        self.assertNotIn("functions", candidate.parts)
        self.assertFalse((ROOT / "functions").exists())
        self.assertNotIn("onRequest", source)
        self.assertNotIn("export default", source)
        self.assertNotIn("console.", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("CF-Connecting-IP", source)

    def test_no_rate_limit_binding_or_activation_config_is_added(self):
        wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
        self.assertNotIn("[[ratelimits]]", wrangler)
        self.assertNotIn("RATE_LIMITER", wrangler)
        source = (
            ROOT / "runtime-candidates" / "affiliate-rate-limit-adapter.mjs"
        ).read_text(encoding="utf-8")
        self.assertNotIn("affiliate_enabled", source)
        self.assertNotIn("eligible", source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_rate_limit_adapter_harness.mjs")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
