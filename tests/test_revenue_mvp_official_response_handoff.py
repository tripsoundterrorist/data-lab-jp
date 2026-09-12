from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import official_blocker_policy as policy  # noqa: E402
import official_response_intake as intake  # noqa: E402
import revenue_mvp_official_response_handoff as handoff  # noqa: E402


def response(blocker=policy.LIFECYCLE_BLOCKER):
    questions = (
        intake.LIFECYCLE_QUESTION_IDS
        if blocker == policy.LIFECYCLE_BLOCKER else intake.SORT_QUESTION_IDS
    )
    return {
        "intake_version": intake.INTAKE_VERSION,
        "registry_version": policy.POLICY_VERSION,
        "received_at": "2026-09-12T12:00:00+09:00",
        "source_type": policy.DIRECT_SUPPORT_CONFIRMATION,
        "source_authority": "DMM_AFFILIATE_SUPPORT",
        "referenced_blocker": blocker,
        "answered_questions": {question: intake.RESOLVED for question in questions},
        "unanswered_questions": [],
        "explicit_confirmations": list(questions),
        "explicit_denials": [],
        "ambiguity_flags": [],
        "safe_reference": "support-response-20260912",
        "prior_question_statuses": {},
    }


class RevenueMvpOfficialResponseHandoffTests(unittest.TestCase):
    def test_complete_lifecycle_response_requires_separate_review(self):
        result = handoff.handoff(response())
        self.assertEqual(result.status, handoff.READY_FOR_REVIEW)
        self.assertEqual(result.resolved_question_count, 9)
        self.assertTrue(result.gate_unlock_candidate)
        self.assertTrue(result.manual_review_required)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_complete_sort_response_requires_separate_review(self):
        result = handoff.handoff(response(policy.SORT_BLOCKER))
        self.assertEqual(result.status, handoff.READY_FOR_REVIEW)
        self.assertEqual(result.resolved_question_count, 8)
        self.assertFalse(result.gate_mutation_allowed)

    def test_partial_response_stays_incomplete(self):
        value = response()
        question = intake.LIFECYCLE_QUESTION_IDS[-1]
        value["answered_questions"].pop(question)
        value["explicit_confirmations"].remove(question)
        value["unanswered_questions"] = [question]
        result = handoff.handoff(value)
        self.assertEqual(result.status, handoff.RESPONSE_INCOMPLETE)
        self.assertFalse(result.gate_unlock_candidate)

    def test_schema_drift_and_unsafe_fields_fail_closed(self):
        cases = []
        missing = response()
        missing.pop("safe_reference")
        cases.append(missing)
        extra = response()
        extra["raw_email_body"] = "fixture"
        cases.append(extra)
        unsafe = response()
        unsafe["safe_reference"] = "https://example.invalid/private"
        cases.append(unsafe)
        wrong_type = response()
        wrong_type["explicit_confirmations"] = tuple(
            wrong_type["explicit_confirmations"]
        )
        cases.append(wrong_type)
        for value in cases:
            with self.subTest(keys=sorted(value)):
                result = handoff.handoff(value)
                self.assertEqual(result.status, handoff.FAIL_CLOSED)
                self.assertFalse(result.gate_mutation_allowed)
                self.assertFalse(result.production_activation_allowed)

    def test_output_never_echoes_supplied_content(self):
        value = response()
        value["safe_reference"] = "private-free-text-marker"
        rendered = json.dumps(handoff.handoff(value).to_dict()).casefold()
        self.assertNotIn("private-free-text-marker", rendered)
        self.assertNotIn("answered_questions", rendered)


if __name__ == "__main__":
    unittest.main()
