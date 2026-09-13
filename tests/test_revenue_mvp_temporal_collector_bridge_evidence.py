from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_collector_bridge_evidence as evidence  # noqa: E402


class TemporalCollectorBridgeEvidenceTests(unittest.TestCase):
    def test_current_fixture_only_bridge_passes_all_checks(self):
        result = evidence.assess_bridge_evidence()
        self.assertEqual(result.status, evidence.READY)
        self.assertEqual((result.checks_passed, result.checks_required), (8, 8))
        self.assertTrue(result.isolated_implementation_verified)
        self.assertEqual(result.fixture_fetch_count, 4)
        self.assertTrue(result.test_filesystem_access_performed)
        self.assertFalse(result.live_api_request_performed)
        self.assertFalse(result.credentials_loaded)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.affiliate_activation_allowed)
        self.assertEqual(result.next_gate, evidence.NEXT_GATE)

    def test_changed_design_fails_closed(self):
        changed = mock.Mock(
            status=evidence.design.BLOCKED,
            implementation_authorized=False,
            api_request_authorized=False,
            scheduler_change_authorized=False,
        )
        with mock.patch.object(evidence.design, "assess_design", return_value=changed):
            result = evidence.assess_bridge_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.isolated_implementation_verified)

    def test_internal_error_is_sanitized(self):
        with mock.patch.object(
            evidence.design, "assess_design", side_effect=RuntimeError("secret-value")
        ):
            result = evidence.assess_bridge_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertNotIn("secret-value", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
