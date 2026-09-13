from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_live_api_fetcher_contract_review as review  # noqa: E402


class LiveApiFetcherContractReviewTests(unittest.TestCase):
    def test_current_contract_allows_only_inert_implementation(self):
        result = review.review_contract()
        self.assertEqual(result.status, review.READY_BLOCKED)
        self.assertTrue(result.bridge_evidence_verified)
        self.assertTrue(result.fixed_request_contract_verified)
        self.assertTrue(result.official_response_pending)
        self.assertFalse(result.official_sort_semantics_resolved)
        self.assertTrue(result.inert_implementation_allowed)
        self.assertFalse(result.live_api_request_authorized)
        self.assertFalse(result.credentials_access_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)
        self.assertEqual(result.next_gate, review.NEXT_GATE)

    def test_permissive_or_resolved_followup_shape_blocks(self):
        current = review.followup.current_status()
        changed = mock.Mock(**{**current.__dict__, "gate_unlock_allowed": True})
        with mock.patch.object(review.followup, "current_status", return_value=changed):
            result = review.review_contract()
        self.assertEqual(result.status, review.BLOCKED)
        self.assertFalse(result.inert_implementation_allowed)

    def test_internal_error_is_sanitized(self):
        with mock.patch.object(
            review.bridge_evidence,
            "assess_bridge_evidence",
            side_effect=RuntimeError("credential-value"),
        ):
            result = review.review_contract()
        self.assertEqual(result.status, review.BLOCKED)
        self.assertNotIn("credential-value", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
