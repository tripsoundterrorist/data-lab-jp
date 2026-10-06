from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import photo_book_compliance_questionnaire as subject  # noqa: E402


def structure():
    return subject.structure_audit.PhotoBookStructureAudit(
        subject.structure_audit.VERSION,
        subject.structure_audit.READY,
        263,
        263,
        263,
        263,
        263,
        263,
        263,
        252,
        263,
        0,
        0,
        39,
        (),
        0,
        False,
        False,
        False,
        False,
        False,
        ("FIXTURE",),
    )


def rights():
    return subject.rights_audit.PhotoBookRightsScopeAudit(
        subject.rights_audit.VERSION,
        subject.rights_audit.READY,
        tuple(subject.rights_audit.REUSE_CANDIDATE_MAPPINGS),
        subject.rights_audit.INTERNAL_ONLY_FIELDS,
        subject.rights_audit.SCOPE_REVIEW_FIELDS,
        tuple(subject.rights_audit.PROHIBITED_MAPPINGS),
        "0.1",
        False,
        False,
        False,
        False,
        False,
        False,
        ("FIXTURE",),
    )


class PhotoBookComplianceQuestionnaireTests(unittest.TestCase):
    def test_ready_questionnaire_is_minimal_unsent_and_keeps_image_closed(self):
        result = subject.compose(structure(), rights())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 263)
        self.assertEqual(result.question_count, 4)
        self.assertEqual(
            tuple(row.question_id for row in result.questions),
            tuple(row.question_id for row in subject.QUESTIONS),
        )
        self.assertFalse(result.send_authorized)
        self.assertFalse(result.external_send_performed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertIn(
            "DMM_BOOKS_IMAGE_PROHIBITION_PRESERVED_PENDING_EXPLICIT_UPDATE",
            result.reason_codes,
        )
        self.assertIn(
            "SEND_DEFERRED_UNTIL_BOOKS_NEXT_RESPONSE_REVIEWED",
            result.reason_codes,
        )

    def test_confirmed_or_nonready_input_fails_closed(self):
        confirmed = replace(rights(), exact_photo_book_scope_confirmed=True)
        image_open = replace(rights(), image_display_allowed=True)
        not_ready = replace(structure(), status=subject.structure_audit.FAIL_CLOSED)
        for values in (
            (not_ready, rights()),
            (structure(), confirmed),
            (structure(), image_open),
            ({}, rights()),
        ):
            with self.subTest(values=values):
                result = subject.compose(*values)
                self.assertEqual(result.status, subject.FAIL_CLOSED)
                self.assertFalse(result.publication_allowed)

    def test_assess_handles_dependency_error(self):
        with mock.patch.object(subject.structure_audit, "assess", side_effect=RuntimeError):
            result = subject.assess(Path("missing"), Path("missing"))
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
