from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import books_next_compliance_followup_packet as subject  # noqa: E402


class BooksNextComplianceFollowupPacketTests(unittest.TestCase):
    def test_packet_has_one_comic_residual_and_four_bl_questions(self):
        packet = subject.build()
        self.assertEqual(packet.question_count, 5)
        self.assertEqual(packet.questions[0], subject.EBOOK_COMIC_RESIDUAL)
        self.assertEqual(
            tuple(row.question_id for row in packet.questions[1:]),
            tuple(row.question_id for row in subject.ebook_bl.QUESTIONS),
        )
        self.assertEqual(
            tuple(row.scope for row in packet.questions),
            ("FANZA/ebook/comic/ebook_comic",) + ("FANZA/ebook/BL",) * 4,
        )

    def test_packet_is_non_sending_and_fail_closed(self):
        packet = subject.build()
        self.assertEqual(packet.status, subject.READY)
        self.assertFalse(packet.send_authorized)
        self.assertFalse(packet.external_send_performed)
        self.assertFalse(packet.compliance_approved)
        self.assertFalse(packet.publication_allowed)
        self.assertFalse(packet.affiliate_allowed)
        self.assertFalse(packet.production_write_allowed)

    def test_question_ids_are_unique_and_scope_is_minimal(self):
        packet = subject.build()
        ids = tuple(row.question_id for row in packet.questions)
        self.assertEqual(len(ids), len(set(ids)))
        rendered = " ".join(row.prompt_ja for row in packet.questions)
        self.assertNotIn("写真集", rendered)
        self.assertNotIn("同人", rendered)

    def test_packet_has_no_links_or_sensitive_identifiers(self):
        rendered = str(subject.build().to_dict()).casefold()
        for forbidden in (
            "http://",
            "https://",
            "affiliate_id",
            "api_id",
            "password",
            "cookie",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
