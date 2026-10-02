from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_compliance_handoff as subject  # noqa: E402


def entity_result(count: int = 3):
    return mock.Mock(status=subject.entity_audit.READY, item_count=count)


def projection_result(count: int = 3, blocked: int = 0):
    return mock.Mock(
        status=subject.projection_audit.READY,
        item_count=count,
        structure_ready_count=count - blocked,
        structure_blocked_count=blocked,
    )


def rights_result():
    return mock.Mock(status=subject.rights_audit.READY)


class DoujinComplianceHandoffTests(unittest.TestCase):
    def test_ready_handoff_is_sanitized_and_non_sending(self):
        result = subject.compose(entity_result(), projection_result(), rights_result())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.question_ids, subject.QUESTION_IDS)
        self.assertEqual(result.question_count, len(subject.QUESTION_IDS))
        self.assertFalse(result.external_send_performed)
        self.assertFalse(result.repository_write_performed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)

    def test_structure_blocker_is_preserved_for_review(self):
        result = subject.compose(entity_result(), projection_result(blocked=1), rights_result())
        self.assertEqual(result.status, subject.READY)
        self.assertIn("STRUCTURE_BLOCKERS_PRESENT", result.reason_codes)
        self.assertFalse(result.publication_allowed)

    def test_count_mismatch_fails_closed(self):
        result = subject.compose(entity_result(2), projection_result(3), rights_result())
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.question_ids, ())

    def test_nonready_input_fails_closed(self):
        entities = entity_result()
        entities.status = subject.entity_audit.FAIL_CLOSED
        result = subject.compose(entities, projection_result(), rights_result())
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
