from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_inert_fetcher_evidence as evidence  # noqa: E402


class TemporalInertFetcherEvidenceTests(unittest.TestCase):
    def test_candidate_passes_all_checks_but_waits_for_official_response(self):
        result = evidence.assess_inert_fetcher()
        self.assertEqual(result.status, evidence.READY_WAITING)
        self.assertEqual((result.checks_passed, result.checks_required), (9, 9))
        self.assertTrue(result.fixed_requests_verified)
        self.assertTrue(result.response_reduction_verified)
        self.assertTrue(result.bounded_failures_verified)
        self.assertTrue(result.official_response_pending)
        self.assertFalse(result.live_api_request_performed)
        self.assertFalse(result.credentials_loaded)
        self.assertFalse(result.state_write_performed)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)
        self.assertEqual(result.next_gate, evidence.NEXT_GATE)

    def test_changed_contract_fails_closed(self):
        changed = mock.Mock(
            status=evidence.contract.BLOCKED,
            inert_implementation_allowed=False,
            live_api_request_authorized=False,
            credentials_access_authorized=False,
        )
        with mock.patch.object(evidence.contract, "review_contract", return_value=changed):
            result = evidence.assess_inert_fetcher()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertIsNone(result.next_gate)

    def test_internal_error_is_sanitized(self):
        with mock.patch.object(
            evidence.candidate, "prepare_request", side_effect=RuntimeError("private-secret")
        ):
            result = evidence.assess_inert_fetcher()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertNotIn("private-secret", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
