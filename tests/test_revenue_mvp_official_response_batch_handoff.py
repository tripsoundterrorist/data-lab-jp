from pathlib import Path
from contextlib import redirect_stdout
import copy
import io
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import official_blocker_policy as policy  # noqa: E402
import official_response_intake as intake  # noqa: E402
import revenue_mvp_official_response_batch_handoff as batch  # noqa: E402


def response(blocker):
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


def complete_batch():
    return [response(policy.LIFECYCLE_BLOCKER), response(policy.SORT_BLOCKER)]


class RevenueMvpOfficialResponseBatchHandoffTests(unittest.TestCase):
    def test_repository_template_has_exact_scopes_and_cannot_advance(self):
        template_path = (
            ROOT / "docs" / "examples"
            / "revenue-mvp-official-response-batch-template-v0.1.json"
        )
        value = json.loads(template_path.read_text(encoding="utf-8"))
        self.assertEqual(len(value), 2)
        self.assertEqual(
            set(value[0]["unanswered_questions"]),
            set(intake.LIFECYCLE_QUESTION_IDS),
        )
        self.assertEqual(
            set(value[1]["unanswered_questions"]),
            set(intake.SORT_QUESTION_IDS),
        )
        result = batch.handoff_batch(value)
        self.assertEqual(result.status, batch.FAIL_CLOSED)
        self.assertFalse(result.combined_gate_review_candidate)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_both_complete_scopes_require_combined_separate_review(self):
        result = batch.handoff_batch(complete_batch())
        self.assertEqual(result.status, batch.READY_FOR_COMBINED_REVIEW)
        self.assertEqual(result.lifecycle_resolved_question_count, 9)
        self.assertEqual(result.sort_resolved_question_count, 8)
        self.assertEqual(result.total_unresolved_question_count, 0)
        self.assertTrue(result.combined_gate_review_candidate)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_one_partial_scope_blocks_combined_review(self):
        value = complete_batch()
        question = intake.SORT_QUESTION_IDS[-1]
        value[1]["answered_questions"].pop(question)
        value[1]["explicit_confirmations"].remove(question)
        value[1]["unanswered_questions"] = [question]
        result = batch.handoff_batch(value)
        self.assertEqual(result.status, batch.RESPONSE_INCOMPLETE)
        self.assertEqual(result.total_unresolved_question_count, 1)
        self.assertFalse(result.combined_gate_review_candidate)

    def test_duplicate_or_missing_scope_fails_closed(self):
        duplicate = [
            response(policy.LIFECYCLE_BLOCKER),
            response(policy.LIFECYCLE_BLOCKER),
        ]
        for value in ([], [response(policy.LIFECYCLE_BLOCKER)], duplicate):
            with self.subTest(length=len(value)):
                self.assertEqual(batch.handoff_batch(value).status, batch.FAIL_CLOSED)

    def test_invalid_member_fails_entire_batch_closed(self):
        value = complete_batch()
        value[1]["raw_email_body"] = "fixture"
        result = batch.handoff_batch(value)
        self.assertEqual(result.status, batch.FAIL_CLOSED)
        self.assertFalse(result.combined_gate_review_candidate)
        self.assertFalse(result.production_activation_allowed)

    def test_input_is_not_mutated_or_echoed(self):
        value = complete_batch()
        value[0]["safe_reference"] = "private-lifecycle-marker"
        original = copy.deepcopy(value)
        rendered = json.dumps(batch.handoff_batch(value).to_dict()).casefold()
        self.assertEqual(value, original)
        self.assertNotIn("private-lifecycle-marker", rendered)
        self.assertNotIn("answered_questions", rendered)

    def test_cli_reads_only_explicit_local_json_and_returns_bounded_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sanitized-response.json"
            path.write_text(json.dumps(complete_batch()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = batch.main(["--input", str(path)])
        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(rendered)["status"], batch.READY_FOR_COMBINED_REVIEW)
        self.assertNotIn("answered_questions", rendered)
        self.assertNotIn("support-response-20260912", rendered)

    def test_cli_missing_or_malformed_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            malformed = Path(directory) / "malformed.json"
            malformed.write_text("not-json", encoding="utf-8")
            for path in (missing, malformed):
                output = io.StringIO()
                with self.subTest(path=path.name), redirect_stdout(output):
                    exit_code = batch.main(["--input", str(path)])
                result = json.loads(output.getvalue())
                self.assertEqual(exit_code, 2)
                self.assertEqual(result["status"], batch.FAIL_CLOSED)
                self.assertFalse(result["production_activation_allowed"])


if __name__ == "__main__":
    unittest.main()
