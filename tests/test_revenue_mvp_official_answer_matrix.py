from pathlib import Path
import json
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_answer_matrix as matrix  # noqa: E402


def allowed(topics=matrix.TOPIC_IDS):
    return {topic: matrix.AnswerDecision(matrix.ALLOWED) for topic in topics}


class RevenueMvpOfficialAnswerMatrixTests(unittest.TestCase):
    def test_current_unanswered_state_fails_closed(self):
        result = matrix.assess_answer_matrix({})
        self.assertEqual(result.status, "FAIL_CLOSED")
        self.assertFalse(result.core_publication_candidate)
        self.assertFalse(result.sns_operation_candidate)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertEqual(result.counts[matrix.UNKNOWN], 12)

    def test_all_allowed_is_review_candidate_not_unlock(self):
        result = matrix.assess_answer_matrix(allowed())
        self.assertEqual(result.status, "REVIEW_CANDIDATE")
        self.assertTrue(result.core_publication_candidate)
        self.assertTrue(result.sns_operation_candidate)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertTrue(result.manual_review_required)

    def test_unverified_conditional_core_topic_remains_blocked(self):
        entries = allowed()
        entries["API_HISTORY_DISPLAY"] = matrix.AnswerDecision(matrix.CONDITIONALLY_ALLOWED)
        result = matrix.assess_answer_matrix(entries)
        self.assertFalse(result.core_publication_candidate)
        self.assertIn("API_HISTORY_DISPLAY", result.blocking_topic_ids)

    def test_verified_conditional_can_be_review_candidate(self):
        entries = allowed()
        entries["API_HISTORY_DISPLAY"] = matrix.AnswerDecision(
            matrix.CONDITIONALLY_ALLOWED, conditions_verified=True
        )
        result = matrix.assess_answer_matrix(entries)
        self.assertTrue(result.core_publication_candidate)
        self.assertFalse(result.gate_unlock_allowed)

    def test_sns_unknown_does_not_block_core_candidate(self):
        result = matrix.assess_answer_matrix(allowed(matrix.CORE_TOPIC_IDS))
        self.assertTrue(result.core_publication_candidate)
        self.assertFalse(result.sns_operation_candidate)

    def test_unknown_topic_and_invalid_status_fail_closed(self):
        entries = allowed()
        entries["UNLISTED"] = matrix.AnswerDecision(matrix.ALLOWED)
        entries["API_IMAGE_USE"] = matrix.AnswerDecision("PERMITTED")
        result = matrix.assess_answer_matrix(entries)
        self.assertEqual(result.status, "FAIL_CLOSED")
        self.assertIn("UNKNOWN_TOPIC", result.reason_codes)
        self.assertIn("INVALID_DECISION", result.reason_codes)

    def test_nonconditional_verified_flag_is_contradictory(self):
        result = matrix.assess_answer_matrix({
            "API_IMAGE_USE": matrix.AnswerDecision(matrix.ALLOWED, conditions_verified=True)
        })
        self.assertIn("CONTRADICTORY_CONDITION_STATE", result.reason_codes)
        self.assertFalse(result.core_publication_candidate)

    def test_cli_reports_safe_current_state(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / "scripts/revenue_mvp_official_answer_matrix.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["status"], "FAIL_CLOSED")
        self.assertFalse(result["gate_unlock_allowed"])


if __name__ == "__main__":
    unittest.main()
