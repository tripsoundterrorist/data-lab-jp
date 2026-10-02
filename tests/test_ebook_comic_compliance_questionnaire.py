from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_comic_compliance_questionnaire as subject  # noqa: E402


def structure():
    return subject.structure_audit.EbookComicStructureAudit(
        subject.structure_audit.VERSION,
        subject.structure_audit.READY,
        558,
        558,
        558,
        558,
        558,
        558,
        558,
        558,
        558,
        0,
        0,
        84,
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
    return subject.rights_audit.EbookComicRightsScopeAudit(
        subject.rights_audit.VERSION,
        subject.rights_audit.READY,
        tuple(subject.rights_audit.REUSE_CANDIDATE_MAPPINGS),
        subject.rights_audit.INTERNAL_ONLY_FIELDS,
        subject.rights_audit.SCOPE_REVIEW_FIELDS,
        subject.rights_audit.PROHIBITED_FIELDS,
        "0.1",
        False,
        False,
        False,
        False,
        False,
        False,
        ("FIXTURE",),
    )


class EbookComicComplianceQuestionnaireTests(unittest.TestCase):
    def test_ready_questionnaire_is_minimal_and_unsent(self):
        result = subject.compose(structure(), rights())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 558)
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

    def test_confirmed_or_nonready_input_fails_closed(self):
        confirmed = rights()
        confirmed = subject.rights_audit.EbookComicRightsScopeAudit(
            *confirmed.__dict__.values()
        )
        object.__setattr__(confirmed, "exact_ebook_comic_scope_confirmed", True)
        not_ready = structure()
        object.__setattr__(not_ready, "status", subject.structure_audit.FAIL_CLOSED)
        for values in ((not_ready, rights()), (structure(), confirmed), ({}, rights())):
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
