from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_compliance_followup_packet as subject  # noqa: E402


class DoujinComplianceFollowupPacketTests(unittest.TestCase):
    def test_packet_contains_only_recontact_required_questions(self):
        packet = subject.build()
        ids = tuple(row.question_id for row in packet.questions)
        self.assertEqual(ids, subject.evidence_audit.RECONTACT_REQUIRED)
        self.assertEqual(packet.question_count, 5)
        self.assertFalse(packet.send_authorized)
        self.assertFalse(packet.external_send_performed)
        self.assertFalse(packet.publication_allowed)

    def test_internal_and_scope_review_questions_are_excluded(self):
        packet_ids = {row.question_id for row in subject.build().questions}
        self.assertTrue(packet_ids.isdisjoint(subject.evidence_audit.INTERNAL_REVIEW))
        self.assertTrue(packet_ids.isdisjoint(subject.evidence_audit.SCOPE_REVIEW_CANDIDATES))

    def test_evidence_audit_failure_blocks_packet(self):
        failed = mock.Mock(status=subject.evidence_audit.FAIL_CLOSED)
        with mock.patch.object(subject.evidence_audit, "assess", return_value=failed):
            with self.assertRaisesRegex(ValueError, "PRIOR_EVIDENCE_AUDIT_NOT_READY"):
                subject.build()

    def test_packet_has_no_links_or_identifiers(self):
        rendered = str(subject.build().to_dict()).casefold()
        self.assertNotIn("http://", rendered)
        self.assertNotIn("https://", rendered)
        self.assertNotIn("affiliate_id", rendered)
        self.assertNotIn("api_id", rendered)


if __name__ == "__main__":
    unittest.main()
