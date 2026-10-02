from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_compliance_response_intake as subject  # noqa: E402


def response(state: str = subject.ALLOW):
    return subject.SanitizedDoujinComplianceResponse(
        version="0.1",
        received_at="2026-10-02T00:00:00+09:00",
        source_type=subject.DIRECT_SUPPORT,
        source_authority="DMM_AFFILIATE_SUPPORT",
        safe_reference="doujin-scope-review-001",
        question_states={question: state for question in subject.QUESTION_IDS},
        explicitly_answered_question_ids=subject.QUESTION_IDS if state in subject.RESOLVED_STATES else (),
    )


class DoujinComplianceResponseIntakeTests(unittest.TestCase):
    def test_complete_official_response_is_only_decision_candidate(self):
        result = subject.classify(response())
        self.assertEqual(result.status, subject.COMPLETE)
        self.assertTrue(result.separate_compliance_decision_candidate)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.gate_change_allowed)
        self.assertFalse(result.publication_allowed)

    def test_partial_response_remains_pending(self):
        value = response()
        states = dict(value.question_states)
        states[subject.QUESTION_IDS[0]] = subject.UNRESOLVED
        value = subject.SanitizedDoujinComplianceResponse(
            **{**value.__dict__, "question_states": states,
               "explicitly_answered_question_ids": subject.QUESTION_IDS[1:]}
        )
        result = subject.classify(value)
        self.assertEqual(result.status, subject.PARTIAL)
        self.assertEqual(result.unresolved_question_ids, (subject.QUESTION_IDS[0],))

    def test_contradiction_is_not_approved(self):
        value = response()
        states = dict(value.question_states)
        states[subject.QUESTION_IDS[1]] = subject.CONFLICT
        value = subject.SanitizedDoujinComplianceResponse(
            **{**value.__dict__, "question_states": states,
               "explicitly_answered_question_ids": subject.QUESTION_IDS[:1] + subject.QUESTION_IDS[2:]}
        )
        result = subject.classify(value)
        self.assertEqual(result.status, subject.CONTRADICTORY)
        self.assertFalse(result.separate_compliance_decision_candidate)

    def test_inferred_resolution_and_unsafe_reference_fail_closed(self):
        value = response()
        value = subject.SanitizedDoujinComplianceResponse(
            **{**value.__dict__, "explicitly_answered_question_ids": ()}
        )
        self.assertEqual(subject.classify(value).status, subject.FAIL_CLOSED)
        unsafe = response()
        unsafe = subject.SanitizedDoujinComplianceResponse(
            **{**unsafe.__dict__, "safe_reference": "https://example.invalid/raw"}
        )
        self.assertEqual(subject.classify(unsafe).status, subject.FAIL_CLOSED)

    def test_raw_mapping_is_rejected(self):
        self.assertEqual(subject.classify({"raw_response": "text"}).status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
