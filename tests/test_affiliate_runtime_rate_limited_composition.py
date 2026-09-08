from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateRuntimeRateLimitedCompositionTests(unittest.TestCase):
    def test_candidate_is_non_deployed_and_has_no_direct_side_effects(self):
        candidate = (
            ROOT / "runtime-candidates"
            / "affiliate-runtime-rate-limited-composition.mjs"
        )
        source = candidate.read_text(encoding="utf-8")
        self.assertTrue(candidate.is_file())
        self.assertNotIn("functions", candidate.parts)
        self.assertFalse((ROOT / "functions").exists())
        self.assertNotIn("onRequest", source)
        self.assertNotIn("export default", source)
        self.assertNotIn("console.", source)
        self.assertNotIn("fetch(", source)

    def test_candidate_composes_existing_fail_closed_boundaries(self):
        source = (
            ROOT / "runtime-candidates"
            / "affiliate-runtime-rate-limited-composition.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn("assessCloudflareCandidate", source)
        self.assertIn("assessAffiliateRateLimit", source)
        self.assertIn("runAffiliateRuntimeCandidate", source)
        self.assertNotIn("affiliate_enabled", source)
        self.assertNotIn("INSERT", source)
        self.assertNotIn("UPDATE", source)
        self.assertNotIn("DELETE", source)

    def test_no_binding_or_activation_config_is_added(self):
        wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
        self.assertNotIn("AFFILIATE_ROUTE_RATE_LIMITER", wrangler)
        self.assertNotIn("[[ratelimits]]", wrangler)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        result = subprocess.run(
            [node, str(
                ROOT / "tests"
                / "affiliate_runtime_rate_limited_composition_harness.mjs"
            )],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
