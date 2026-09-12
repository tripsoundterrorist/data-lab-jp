from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_launch_rehearsal as rehearsal  # noqa: E402


class RevenueMvpLaunchRehearsalTests(unittest.TestCase):
    def test_offline_future_path_passes_all_checks(self):
        result = rehearsal.run_rehearsal()
        self.assertEqual(result.status, rehearsal.PASS)
        self.assertEqual((result.checks_passed, result.checks_required), (5, 5))
        self.assertTrue(result.future_gate_path_verified)
        self.assertTrue(result.d1_enable_and_rollback_verified)
        self.assertTrue(result.worker_redirect_candidate_verified)
        self.assertTrue(result.activation_order_verified)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.network_request_performed)
        self.assertFalse(result.deploy_allowed)
        self.assertFalse(result.paid_plan_change_allowed)

    def test_missing_node_fails_closed(self):
        with mock.patch.object(rehearsal.shutil, "which", return_value=None):
            result = rehearsal.run_rehearsal()
        self.assertEqual(result.status, rehearsal.BLOCKED)
        self.assertFalse(result.worker_redirect_candidate_verified)
        self.assertFalse(result.deploy_allowed)

    def test_gate_failure_cannot_be_hidden_by_other_checks(self):
        with mock.patch.object(rehearsal, "_future_gate_path", return_value=False):
            result = rehearsal.run_rehearsal()
        self.assertEqual(result.status, rehearsal.BLOCKED)
        self.assertEqual(result.checks_passed, 4)

    def test_safe_result_contains_no_fixture_identifiers_or_paths(self):
        rendered = json.dumps(rehearsal.run_rehearsal().to_dict()).casefold()
        for forbidden in ("fixture-content", "itm_0123", str(ROOT).casefold(), "https://"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
