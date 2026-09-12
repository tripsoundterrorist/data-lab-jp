from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_response_rehearsal as rehearsal  # noqa: E402


class RevenueMvpOfficialResponseRehearsalTests(unittest.TestCase):
    def test_all_response_scenarios_pass_without_unlock(self):
        result = rehearsal.run_rehearsal()
        self.assertEqual(result.status, rehearsal.PASS)
        self.assertEqual((result.checks_passed, result.checks_required), (7, 7))
        self.assertTrue(result.complete_lifecycle_candidate_verified)
        self.assertTrue(result.complete_sort_candidate_verified)
        self.assertTrue(result.partial_response_blocked)
        self.assertTrue(result.ambiguous_response_review_required)
        self.assertTrue(result.contradictory_response_review_required)
        self.assertTrue(result.unsafe_raw_input_blocked)
        self.assertTrue(result.no_gate_mutation_verified)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_classifier_failure_is_bounded_and_fail_closed(self):
        with mock.patch.object(
            rehearsal.intake,
            "classify_official_response",
            side_effect=RuntimeError("private response"),
        ):
            result = rehearsal.run_rehearsal()
        self.assertEqual(result.status, rehearsal.BLOCKED)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertNotIn("private response", json.dumps(result.to_dict()))

    def test_safe_result_exposes_no_response_or_contact_data(self):
        rendered = json.dumps(rehearsal.run_rehearsal().to_dict()).casefold()
        for forbidden in ("raw_email", "sender", "dmm_affiliate_support", "followup-response"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
