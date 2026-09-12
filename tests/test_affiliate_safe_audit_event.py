from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateSafeAuditEventTests(unittest.TestCase):
    def test_candidate_is_non_deployed_and_cannot_emit_logs(self):
        candidate = ROOT / "runtime-candidates" / "affiliate-safe-audit-event.mjs"
        source = candidate.read_text(encoding="utf-8")
        self.assertTrue(candidate.is_file())
        self.assertNotIn("functions", candidate.parts)
        self.assertFalse((ROOT / "functions").exists())
        self.assertNotIn("onRequest", source)
        self.assertNotIn("export default", source)
        self.assertNotIn("console.", source)
        self.assertNotIn("fetch(", source)

    def test_candidate_enforces_exact_bounded_input_shape(self):
        source = (
            ROOT / "runtime-candidates" / "affiliate-safe-audit-event.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn('Object.keys(candidate).sort().join(",")', source)
        self.assertIn('"event,reasonCodes,status"', source)
        self.assertIn("UNSAFE_AUDIT_EVENT_REJECTED", source)

    def test_deployment_preflight_remains_fail_closed(self):
        source = (
            ROOT / "scripts" / "affiliate_runtime_deployment_preflight.py"
        ).read_text(encoding="utf-8")
        self.assertIn("log_redaction_enabled=True", source)

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed or is not available on PATH")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_safe_audit_event_harness.mjs")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
