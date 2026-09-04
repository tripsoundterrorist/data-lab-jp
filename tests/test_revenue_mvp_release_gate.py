from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_release_gate as gate  # noqa: E402


class RevenueMvpReleaseGateTests(unittest.TestCase):
    def test_current_state_reports_exact_release_blockers(self):
        result = gate.run_gate()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.production_release_allowed)
        self.assertFalse(result.affiliate_integration_allowed)
        self.assertEqual(result.shell_status, "SHELL_VALIDATED")
        self.assertEqual(result.public_data_state, "UNPUBLISHED")
        self.assertIn("REVENUE_MVP_RELEASE_BLOCKED", result.reason_codes)
        self.assertIn("WAIT_FOR_DMM_LIFECYCLE_RESPONSE", result.next_actions)
        self.assertIn("WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE", result.next_actions)

    def test_deployment_ready_cannot_override_official_blockers(self):
        deployment = SimpleNamespace(
            status="READY", public_data_state="APPROVED_CANDIDATE",
            public_data_deployment_allowed=True, reason_codes=(),
        )
        with mock.patch.object(
            gate.revenue_mvp_deployment_preflight, "run_preflight",
            return_value=deployment,
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.affiliate_integration_allowed)

    def test_internal_failure_is_bounded_and_fail_closed(self):
        with mock.patch.object(
            gate.revenue_mvp_deployment_preflight, "run_preflight",
            side_effect=RuntimeError("secret URL"),
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertFalse(result.production_release_allowed)
        self.assertNotIn("secret", json.dumps(result.to_dict()))

    def test_cli_is_read_only_and_machine_readable(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / "scripts/revenue_mvp_release_gate.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["status"], gate.BLOCKED)
        self.assertFalse(result["production_release_allowed"])


if __name__ == "__main__":
    unittest.main()
