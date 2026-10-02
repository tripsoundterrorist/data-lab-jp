from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_comic_compliance_response_intake as subject  # noqa: E402


def response(state: str = subject.ALLOW):
    return subject.SanitizedEbookComicComplianceResponse(
        version=subject.VERSION,
        received_at="2026-10-03T00:00:00+09:00",
        source_type=subject.DIRECT_SUPPORT,
        source_authority="DMM_AFFILIATE_SUPPORT",
        safe_reference="ebook-comic-scope-review-001",
        question_states={question: state for question in subject.QUESTION_IDS},
        explicitly_answered_question_ids=(
            subject.QUESTION_IDS if state in subject.RESOLVED_STATES else ()
        ),
    )


class EbookComicComplianceResponseIntakeTests(unittest.TestCase):
    def test_complete_response_is_only_separate_decision_candidate(self):
        result = subject.classify(response())
        self.assertEqual(result.status, subject.COMPLETE)
        self.assertTrue(result.separate_compliance_decision_candidate)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.gate_change_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_partial_response_stays_pending(self):
        value = response()
        states = dict(value.question_states)
        states[subject.QUESTION_IDS[0]] = subject.UNRESOLVED
        value = subject.SanitizedEbookComicComplianceResponse(
            **{
                **value.__dict__,
                "question_states": states,
                "explicitly_answered_question_ids": subject.QUESTION_IDS[1:],
            }
        )
        result = subject.classify(value)
        self.assertEqual(result.status, subject.PARTIAL)
        self.assertEqual(result.unresolved_question_ids, (subject.QUESTION_IDS[0],))
        self.assertFalse(result.publication_allowed)

    def test_contradiction_blocks_decision_candidate(self):
        value = response()
        states = dict(value.question_states)
        states[subject.QUESTION_IDS[1]] = subject.CONFLICT
        value = subject.SanitizedEbookComicComplianceResponse(
            **{
                **value.__dict__,
                "question_states": states,
                "explicitly_answered_question_ids": (
                    subject.QUESTION_IDS[:1] + subject.QUESTION_IDS[2:]
                ),
            }
        )
        result = subject.classify(value)
        self.assertEqual(result.status, subject.CONTRADICTORY)
        self.assertFalse(result.separate_compliance_decision_candidate)

    def test_inferred_resolution_and_unsafe_reference_fail_closed(self):
        value = response()
        inferred = subject.SanitizedEbookComicComplianceResponse(
            **{**value.__dict__, "explicitly_answered_question_ids": ()}
        )
        self.assertEqual(subject.classify(inferred).status, subject.FAIL_CLOSED)
        unsafe = subject.SanitizedEbookComicComplianceResponse(
            **{**value.__dict__, "safe_reference": "https://example.invalid/raw"}
        )
        self.assertEqual(subject.classify(unsafe).status, subject.FAIL_CLOSED)

    def test_raw_mapping_and_unknown_question_fail_closed(self):
        self.assertEqual(subject.classify({"raw_response": "text"}).status, subject.FAIL_CLOSED)
        value = response()
        states = dict(value.question_states)
        states["UNKNOWN"] = subject.ALLOW
        changed = subject.SanitizedEbookComicComplianceResponse(
            **{**value.__dict__, "question_states": states}
        )
        self.assertEqual(subject.classify(changed).status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
