from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_bl_compliance_questionnaire as subject  # noqa: E402


def structure():
    return subject.structure_audit.EbookBlStructureAudit(
        version=subject.structure_audit.VERSION,
        status=subject.structure_audit.READY,
        item_count=107,
        latest_snapshot_count=107,
        source_namespace_valid_count=107,
        items_with_title=107,
        items_with_release_date=107,
        items_with_product_url=107,
        items_with_https_image=107,
        items_with_series=107,
        items_with_genre=107,
        items_with_current_price=107,
        items_with_list_price=0,
        items_with_discount=0,
        items_with_review=10,
        contributor_roles=(),
        malformed_json_item_count=0,
        entity_semantics_confirmed=False,
        field_rights_confirmed=False,
        database_write_performed=False,
        publication_allowed=False,
        production_write_allowed=False,
        reason_codes=("FIXTURE",),
    )


def rights():
    return subject.rights_audit.EbookBlRightsScopeAudit(
        version=subject.rights_audit.VERSION,
        status=subject.rights_audit.READY,
        reuse_candidate_fields=tuple(subject.rights_audit.REUSE_CANDIDATE_MAPPINGS),
        internal_only_fields=subject.rights_audit.INTERNAL_ONLY_FIELDS,
        scope_review_required_fields=subject.rights_audit.SCOPE_REVIEW_FIELDS,
        prohibited_fields=subject.rights_audit.PROHIBITED_FIELDS,
        source_policy_version="0.1",
        exact_ebook_bl_scope_confirmed=False,
        contributor_semantics_confirmed=False,
        image_scope_confirmed=False,
        field_rights_confirmed=False,
        publication_allowed=False,
        gate_change_allowed=False,
        reason_codes=("FIXTURE",),
    )


class EbookBlComplianceQuestionnaireTests(unittest.TestCase):
    def test_ready_questionnaire_is_minimal_deferred_and_unsent(self):
        result = subject.compose(structure(), rights())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 107)
        self.assertEqual(result.question_count, 4)
        self.assertEqual(
            tuple(row.question_id for row in result.questions),
            tuple(row.question_id for row in subject.QUESTIONS),
        )
        self.assertIn(
            "DEFER_UNTIL_CURRENT_INQUIRY_RESPONSE_REVIEWED", result.reason_codes
        )
        self.assertFalse(result.send_authorized)
        self.assertFalse(result.external_send_performed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)

    def test_confirmed_or_nonready_input_fails_closed(self):
        confirmed = replace(rights(), exact_ebook_bl_scope_confirmed=True)
        not_ready = replace(structure(), status=subject.structure_audit.FAIL_CLOSED)
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

