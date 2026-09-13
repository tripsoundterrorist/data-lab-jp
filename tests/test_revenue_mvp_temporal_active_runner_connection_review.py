from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_active_runner_connection_review as review  # noqa: E402


class TemporalActiveRunnerConnectionReviewTests(unittest.TestCase):
    def test_current_evidence_is_ready_only_for_explicit_approval(self):
        result = review.review_active_runner_connection()
        self.assertEqual(result.status, review.READY)
        self.assertEqual((result.checks_passed, result.checks_required), (2, 2))
        self.assertTrue(result.design_verified)
        self.assertTrue(result.isolated_candidate_verified)
        self.assertEqual(result.next_gate, review.NEXT_GATE)
        self.assertFalse(result.active_connection_authorized)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_incomplete_candidate_blocks_without_authority(self):
        changed = mock.Mock(
            version=review.evidence.VERSION,
            status=review.evidence.BLOCKED,
            checks_passed=7,
            checks_required=8,
            implementation_evidence_candidate=False,
            test_filesystem_access_performed=False,
            active_pipeline_connected=False,
            api_request_authorized=False,
            production_write_authorized=False,
            scheduler_change_authorized=False,
            deploy_allowed=False,
        )
        with mock.patch.object(
            review.evidence, "assess_candidate_evidence", return_value=changed
        ):
            result = review.review_active_runner_connection()
        self.assertEqual(result.status, review.BLOCKED)
        self.assertIsNone(result.next_gate)
        self.assertFalse(result.active_connection_authorized)

    def test_permissive_candidate_blocks(self):
        current = review.evidence.assess_candidate_evidence()
        with mock.patch.object(
            review.evidence,
            "assess_candidate_evidence",
            return_value=mock.Mock(**{
                **current.__dict__, "active_pipeline_connected": True,
            }),
        ):
            result = review.review_active_runner_connection()
        self.assertEqual(result.status, review.BLOCKED)

    def test_internal_error_is_sanitized(self):
        with mock.patch.object(
            review.design, "assess_design", side_effect=RuntimeError("private-path")
        ):
            result = review.review_active_runner_connection()
        self.assertEqual(result.status, review.BLOCKED)
        self.assertNotIn("private-path", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
