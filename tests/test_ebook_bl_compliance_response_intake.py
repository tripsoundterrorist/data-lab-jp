from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_bl_compliance_response_intake as subject  # noqa: E402


def response(state: str = subject.ALLOW):
    return subject.SanitizedEbookBlComplianceResponse(
        version=subject.VERSION,
        received_at="2026-10-05T01:30:00+09:00",
        source_type=subject.DIRECT_SUPPORT,
        source_authority="DMM_AFFILIATE_SUPPORT",
        safe_reference="ebook-bl-scope-review-001",
        question_states={question: state for question in subject.QUESTION_IDS},
        explicitly_answered_question_ids=(
            subject.QUESTION_IDS if state in subject.RESOLVED_STATES else ()
        ),
    )


class EbookBlComplianceResponseIntakeTests(unittest.TestCase):
    def test_complete_response_is_only_separate_decision_candidate(self):
        result = subject.classify(response())
        self.assertEqual(result.status, subject.COMPLETE)
        self.assertTrue(result.separate_compliance_decision_candidate)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.gate_change_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertIn("BL_SCOPE_NOT_INFERRED_FROM_COMIC", result.reason_codes)

    def test_partial_response_stays_pending(self):
        value = response()
        states = dict(value.question_states)
        states[subject.QUESTION_IDS[0]] = subject.UNRESOLVED
        result = subject.classify(
            replace(
                value,
                question_states=states,
                explicitly_answered_question_ids=subject.QUESTION_IDS[1:],
            )
        )
        self.assertEqual(result.status, subject.PARTIAL)
        self.assertEqual(result.unresolved_question_ids, (subject.QUESTION_IDS[0],))

    def test_contradiction_blocks_decision_candidate(self):
        value = response()
        states = dict(value.question_states)
        states[subject.QUESTION_IDS[1]] = subject.CONFLICT
        result = subject.classify(
            replace(
                value,
                question_states=states,
                explicitly_answered_question_ids=(
                    subject.QUESTION_IDS[:1] + subject.QUESTION_IDS[2:]
                ),
            )
        )
        self.assertEqual(result.status, subject.CONTRADICTORY)
        self.assertFalse(result.separate_compliance_decision_candidate)

    def test_inferred_resolution_and_unsafe_reference_fail_closed(self):
        value = response()
        self.assertEqual(
            subject.classify(replace(value, explicitly_answered_question_ids=())).status,
            subject.FAIL_CLOSED,
        )
        self.assertEqual(
            subject.classify(replace(value, safe_reference="https://example.invalid/raw")).status,
            subject.FAIL_CLOSED,
        )

    def test_raw_mapping_and_unknown_question_fail_closed(self):
        self.assertEqual(subject.classify({"raw_response": "text"}).status, subject.FAIL_CLOSED)
        value = response()
        states = dict(value.question_states)
        states["UNKNOWN"] = subject.ALLOW
        self.assertEqual(
            subject.classify(replace(value, question_states=states)).status,
            subject.FAIL_CLOSED,
        )


if __name__ == "__main__":
    unittest.main()
