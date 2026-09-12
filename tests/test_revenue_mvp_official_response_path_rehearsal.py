from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_response_path_rehearsal as rehearsal  # noqa: E402


class RevenueMvpOfficialResponsePathRehearsalTests(unittest.TestCase):
    def test_entire_offline_path_passes_without_mutation(self):
        result = rehearsal.run_rehearsal()
        self.assertEqual(result.status, rehearsal.PASS)
        self.assertEqual((result.checks_passed, result.checks_required), (6, 6))
        self.assertTrue(result.combined_response_handoff_verified)
        self.assertTrue(result.lifecycle_evidence_verified)
        self.assertTrue(result.sort_evidence_verified)
        self.assertTrue(result.manual_gate_review_boundary_verified)
        self.assertTrue(result.partial_response_stop_verified)
        self.assertTrue(result.no_mutation_boundary_verified)
        self.assertFalse(result.network_request_performed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_dependency_failure_is_bounded_and_fail_closed(self):
        with mock.patch.object(
            rehearsal.lifecycle_evidence,
            "assess_lifecycle_condition_evidence",
            side_effect=RuntimeError("private implementation detail"),
        ):
            result = rehearsal.run_rehearsal()
        rendered = json.dumps(result.to_dict()).casefold()
        self.assertEqual(result.status, rehearsal.BLOCKED)
        self.assertNotIn("private implementation detail", rendered)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_safe_output_contains_no_response_or_item_data(self):
        rendered = json.dumps(rehearsal.run_rehearsal().to_dict()).casefold()
        for forbidden in (
            "answered_questions", "safe_reference", "content_id", "raw_email",
            "api_id", "affiliate_id", "https://",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
