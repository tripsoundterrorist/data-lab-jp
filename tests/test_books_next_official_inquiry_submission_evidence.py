import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "books-next-official-inquiry-submission-sanitized-20261006.json"
)


class BooksNextOfficialInquirySubmissionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_records_user_submission_and_waiting_state(self):
        self.assertEqual(
            self.value["status"], "SUBMITTED_AWAITING_OFFICIAL_RESPONSE"
        )
        self.assertEqual(self.value["submitted_on"], "2026-10-06")
        self.assertEqual(self.value["source_type"], "OPERATOR_ATTESTATION")
        self.assertTrue(self.value["submitted_by_user"])
        self.assertFalse(self.value["external_send_performed_by_codex"])
        self.assertFalse(self.value["response_received"])

    def test_exact_scopes_and_question_ids_are_bounded(self):
        self.assertEqual(
            self.value["exact_scopes"],
            ["FANZA/ebook/comic/ebook_comic", "FANZA/ebook/BL"],
        )
        self.assertEqual(self.value["question_count"], 5)
        self.assertEqual(len(self.value["question_ids"]), 5)
        self.assertEqual(len(set(self.value["question_ids"])), 5)

    def test_sensitive_and_raw_material_are_not_stored(self):
        self.assertFalse(self.value["raw_submission_stored"])
        self.assertFalse(self.value["private_inquiry_url_stored"])
        self.assertFalse(self.value["account_identifier_stored"])
        rendered = json.dumps(self.value, ensure_ascii=False).casefold()
        self.assertNotIn("http://", rendered)
        self.assertNotIn("https://", rendered)
        self.assertNotIn("affiliate_id", rendered)
        self.assertNotIn("api_id", rendered)
        self.assertNotIn("password", rendered)
        self.assertNotIn("cookie", rendered)

    def test_all_release_gates_remain_closed(self):
        for field in (
            "compliance_approved",
            "publication_allowed",
            "affiliate_activation_allowed",
            "database_write_allowed",
            "production_write_allowed",
        ):
            self.assertFalse(self.value[field])


if __name__ == "__main__":
    unittest.main()
