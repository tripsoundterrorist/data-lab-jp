from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_answer_batch as batch  # noqa: E402
import revenue_mvp_official_answer_matrix as matrix  # noqa: E402


def payload(topics=None):
    return {
        "batch_version": "0.1",
        "source_type": "DIRECT_SUPPORT_CONFIRMATION",
        "source_authority": "DMM_AFFILIATE_SUPPORT",
        "received_at": "2026-09-05T00:00:00+09:00",
        "topics": topics or {},
    }


def decision(status=matrix.ALLOWED, *, conditions=False, evidence=True):
    return {
        "status": status,
        "conditions_verified": conditions,
        "evidence_confirmed": evidence,
    }


class OfficialAnswerBatchTests(unittest.TestCase):
    def test_empty_valid_batch_keeps_all_topics_blocked(self):
        result = batch.validate_batch(payload())
        self.assertEqual(result.intake_status, batch.ACCEPTED)
        self.assertFalse(result.core_publication_candidate)
        self.assertEqual(result.blocking_topic_ids, matrix.TOPIC_IDS)

    def test_all_allowed_is_manual_review_candidate_only(self):
        result = batch.validate_batch(payload({
            topic: decision() for topic in matrix.TOPIC_IDS
        }))
        self.assertEqual(result.matrix_status, "REVIEW_CANDIDATE")
        self.assertTrue(result.core_publication_candidate)
        self.assertTrue(result.sns_operation_candidate)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertTrue(result.manual_review_required)

    def test_verified_conditional_is_delegated_to_matrix(self):
        topics = {topic: decision() for topic in matrix.CORE_TOPIC_IDS}
        topics["API_HISTORY_DISPLAY"] = decision(
            matrix.CONDITIONALLY_ALLOWED, conditions=True
        )
        result = batch.validate_batch(payload(topics))
        self.assertTrue(result.core_publication_candidate)
        self.assertIn("API_HISTORY_DISPLAY", result.conditional_topic_ids)

    def test_unverified_allowed_is_rejected(self):
        result = batch.validate_batch(payload({
            "API_IMAGE_USE": decision(evidence=False)
        }))
        self.assertEqual(result.intake_status, batch.FAIL_CLOSED)
        self.assertIn("OFFICIAL_EVIDENCE_REQUIRED", result.reason_codes)

    def test_unverified_conditional_is_rejected(self):
        result = batch.validate_batch(payload({
            "API_HISTORY_DISPLAY": decision(
                matrix.CONDITIONALLY_ALLOWED, evidence=False
            )
        }))
        self.assertEqual(result.intake_status, batch.FAIL_CLOSED)

    def test_unknown_and_follow_up_are_safe_without_evidence(self):
        result = batch.validate_batch(payload({
            "API_HISTORY_DISPLAY": decision(matrix.UNKNOWN, evidence=False),
            "API_IMAGE_USE": decision(matrix.FOLLOW_UP_REQUIRED, evidence=False),
        }))
        self.assertEqual(result.intake_status, batch.ACCEPTED)
        self.assertFalse(result.core_publication_candidate)

    def test_raw_email_and_unknown_keys_are_rejected(self):
        value = payload()
        value["raw_email_body"] = "fixture"
        self.assertEqual(batch.validate_batch(value).intake_status, batch.FAIL_CLOSED)
        value = payload({"UNKNOWN": decision()})
        self.assertIn("UNKNOWN_TOPIC", batch.validate_batch(value).reason_codes)

    def test_nonconditional_condition_flag_is_rejected(self):
        result = batch.validate_batch(payload({
            "API_IMAGE_USE": decision(conditions=True)
        }))
        self.assertIn("CONTRADICTORY_CONDITION_STATE", result.reason_codes)

    def test_result_omits_normalized_entries_and_source_metadata(self):
        result = batch.validate_batch(payload({"API_IMAGE_USE": decision()}))
        serialized = json.dumps(result.to_dict())
        self.assertNotIn("normalized_entries", serialized)
        self.assertNotIn("DMM_AFFILIATE_SUPPORT", serialized)
        self.assertNotIn("received_at", serialized)

    def test_no_mutation_api_and_current_matrix_remains_empty(self):
        batch.validate_batch(payload({"API_IMAGE_USE": decision()}))
        self.assertEqual(dict(matrix.current_entries()), {})
        self.assertFalse(any(
            name.startswith("set_") or name.startswith("update_")
            for name in dir(batch)
        ))

    def test_cli_reads_sanitized_json_and_returns_safe_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sanitized.json"
            path.write_text(json.dumps(payload()), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                return_code = batch.main(["--input", str(path)])
        self.assertEqual(return_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["intake_status"], batch.ACCEPTED)
        self.assertNotIn(str(path), output.getvalue())


if __name__ == "__main__":
    unittest.main()
