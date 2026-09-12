from pathlib import Path
from types import SimpleNamespace
import copy
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_gate_review_packet as packet  # noqa: E402


def inputs():
    response = SimpleNamespace(
        version="0.1", status="READY_FOR_COMBINED_SEPARATE_GATE_REVIEW",
        lifecycle_status="RESOLVED", sort_status="RESOLVED",
        lifecycle_resolved_question_count=9, sort_resolved_question_count=8,
        total_unresolved_question_count=0,
        total_contradictory_question_count=0,
        combined_gate_review_candidate=True, gate_mutation_allowed=False,
        production_activation_allowed=False,
    )
    lifecycle = SimpleNamespace(
        version="0.1", status="IMPLEMENTATION_EVIDENCE_READY",
        implementation_evidence_candidate=True,
        official_semantics_resolved=False,
        publication_gate_unlock_allowed=False,
        checks_passed=5, checks_required=5,
    )
    sort = SimpleNamespace(
        version="0.1", status="IMPLEMENTATION_EVIDENCE_READY",
        implementation_evidence_candidate=True,
        official_semantics_resolved=False,
        publication_gate_unlock_allowed=False,
        checks_passed=6, checks_required=6,
    )
    return response, lifecycle, sort


class RevenueMvpOfficialGateReviewPacketTests(unittest.TestCase):
    def test_complete_response_and_evidence_create_review_candidate_only(self):
        result = packet.build_review_packet(*inputs())
        self.assertEqual(result.status, packet.READY_FOR_MANUAL_REVIEW)
        self.assertTrue(result.lifecycle_gate_pass_candidate)
        self.assertTrue(result.semantics_gate_pass_candidate)
        self.assertTrue(result.manual_gate_review_required)
        self.assertFalse(result.registry_mutation_allowed)
        self.assertFalse(result.publication_gate_unlock_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_each_drift_or_unsafe_state_blocks_review(self):
        cases = (
            (0, "status", "RESPONSE_INCOMPLETE"),
            (0, "total_unresolved_question_count", 1),
            (0, "gate_mutation_allowed", True),
            (1, "implementation_evidence_candidate", False),
            (1, "official_semantics_resolved", True),
            (2, "checks_passed", 5),
            (2, "publication_gate_unlock_allowed", True),
        )
        for index, field, value in cases:
            current = list(inputs())
            current[index] = copy.copy(current[index])
            setattr(current[index], field, value)
            with self.subTest(field=field):
                result = packet.build_review_packet(*current)
                self.assertEqual(result.status, packet.BLOCKED)
                self.assertFalse(result.registry_mutation_allowed)
                self.assertFalse(result.publication_gate_unlock_allowed)
                self.assertFalse(result.production_activation_allowed)

    def test_malformed_input_fails_closed_without_details(self):
        result = packet.build_review_packet(None, None, None)
        rendered = json.dumps(result.to_dict()).casefold()
        self.assertEqual(result.status, packet.BLOCKED)
        for forbidden in ("traceback", "exception", "content_id", "raw_email"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
