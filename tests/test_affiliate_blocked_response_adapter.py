from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateBlockedResponseAdapterTests(unittest.TestCase):
    def test_candidate_is_non_deployed_and_cannot_redirect(self):
        candidate = (
            ROOT / "runtime-candidates" / "affiliate-blocked-response-adapter.mjs"
        )
        source = candidate.read_text(encoding="utf-8")
        self.assertTrue(candidate.is_file())
        self.assertNotIn("functions", candidate.parts)
        self.assertFalse((ROOT / "functions").exists())
        self.assertNotIn("onRequest", source)
        self.assertNotIn("export default", source)
        self.assertNotIn("Response.redirect", source)
        self.assertNotIn('"Location":', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("console.", source)

    def test_only_blocked_statuses_are_allow_listed(self):
        source = (
            ROOT / "runtime-candidates" / "affiliate-blocked-response-adapter.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn("new Set([404, 405, 429])", source)
        self.assertNotIn("new Set([200", source)
        self.assertNotIn("new Set([302", source)
        self.assertIn('"Cache-Control": "no-store, max-age=0"', source)

    def test_deployment_preflight_remains_fail_closed(self):
        source = (
            ROOT / "scripts" / "affiliate_runtime_deployment_preflight.py"
        ).read_text(encoding="utf-8")
        self.assertIn("response_cache_disabled=True", source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        result = subprocess.run(
            [node, str(
                ROOT / "tests" / "affiliate_blocked_response_adapter_harness.mjs"
            )],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
