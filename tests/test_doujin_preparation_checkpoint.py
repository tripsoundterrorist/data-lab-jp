from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_preparation_checkpoint as subject  # noqa: E402


def handoff(count: int = 3, blocked: int = 0):
    return subject.compliance.DoujinComplianceHandoff(
        subject.compliance.VERSION,
        subject.compliance.READY,
        count,
        count - blocked,
        blocked,
        subject.compliance.QUESTION_IDS,
        len(subject.compliance.QUESTION_IDS),
        False,
        False,
        False,
        False,
        ("FIXTURE",),
    )


def prices(count: int = 3, blocked: int = 0):
    return subject.price_audit.DoujinPriceSnapshotAudit(
        subject.price_audit.VERSION,
        subject.price_audit.READY,
        count,
        count - blocked,
        blocked,
        (),
        False,
        False,
        False,
        False,
        False,
        False,
        ("FIXTURE",),
    )


def packet():
    questions = tuple(
        subject.followup.FollowupQuestion(question_id, "確認文")
        for question_id in (
            "DOUJIN_SOURCE_SCOPE_APPLICABILITY",
            "RELEASE_DATE_PUBLIC_DISPLAY",
            "SANITIZED_RAW_RETENTION_ALLOWED",
            "SANITIZED_RAW_RETENTION_DURATION",
            "HISTORICAL_NORMALIZED_PRICE_RETENTION",
        )
    )
    return subject.followup.DoujinComplianceFollowupPacket(
        subject.followup.VERSION,
        "READY_FOR_MANUAL_SEND_REVIEW",
        "件名",
        "冒頭",
        questions,
        "結び",
        len(questions),
        False,
        False,
        False,
        ("FIXTURE",),
    )


class DoujinPreparationCheckpointTests(unittest.TestCase):
    def test_ready_checkpoint_preserves_all_closed_boundaries(self):
        result = subject.compose(handoff(), prices(), packet())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 3)
        self.assertEqual(result.unresolved_official_question_count, 5)
        self.assertEqual(result.p0_review_not_before_jst, "2026-10-10")
        self.assertFalse(result.external_send_performed)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.repository_write_performed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_structure_blockers_are_preserved_without_preventing_pause(self):
        result = subject.compose(handoff(blocked=1), prices(blocked=1), packet())
        self.assertEqual(result.status, subject.READY)
        self.assertIn("TECHNICAL_STRUCTURE_BLOCKERS_PRESENT", result.reason_codes)
        self.assertFalse(result.publication_allowed)

    def test_count_mismatch_or_send_authorization_fails_closed(self):
        invalid_packet = packet()
        invalid_packet = subject.followup.DoujinComplianceFollowupPacket(
            *(
                invalid_packet.version,
                invalid_packet.status,
                invalid_packet.subject_ja,
                invalid_packet.introduction_ja,
                invalid_packet.questions,
                invalid_packet.closing_ja,
                invalid_packet.question_count,
                True,
                invalid_packet.external_send_performed,
                invalid_packet.publication_allowed,
                invalid_packet.reason_codes,
            )
        )
        for values in ((handoff(2), prices(3), packet()), (handoff(), prices(), invalid_packet)):
            with self.subTest(values=values):
                result = subject.compose(*values)
                self.assertEqual(result.status, subject.FAIL_CLOSED)
                self.assertFalse(result.publication_allowed)

    def test_assess_handles_component_failure(self):
        with mock.patch.object(subject.compliance, "assess", side_effect=RuntimeError):
            result = subject.assess(Path("missing"), Path("missing"))
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
