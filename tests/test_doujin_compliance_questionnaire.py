from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_compliance_questionnaire as subject  # noqa: E402


class DoujinComplianceQuestionnaireTests(unittest.TestCase):
    def test_exact_handoff_question_set_is_routed_once(self):
        result = subject.build()
        ids = tuple(row.question_id for row in result.questions)
        self.assertEqual(ids, subject.QUESTION_IDS)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(result.external_send_performed)
        self.assertFalse(result.publication_allowed)

    def test_internal_policy_questions_are_not_routed_to_support(self):
        by_id = {row.question_id: row for row in subject.QUESTIONS}
        self.assertEqual(by_id["OBSERVATION_TIME_PUBLIC_DISPLAY"].owner, subject.INTERNAL)
        self.assertEqual(by_id["DATA_FRESHNESS_PUBLIC_DISPLAY"].owner, subject.INTERNAL)
        self.assertNotEqual(by_id["DOUJIN_SOURCE_SCOPE_APPLICABILITY"].owner, subject.INTERNAL)

    def test_prior_evidence_is_reviewed_before_recontact(self):
        reusable = {row.question_id for row in subject.QUESTIONS if row.prior_evidence_candidate}
        self.assertIn("DOUJIN_SOURCE_SCOPE_APPLICABILITY", reusable)
        self.assertIn("DOUJIN_DEEPLINK_AFFILIATE_METHOD", reusable)
        self.assertNotIn("SANITIZED_RAW_RETENTION_DURATION", reusable)


if __name__ == "__main__":
    unittest.main()
