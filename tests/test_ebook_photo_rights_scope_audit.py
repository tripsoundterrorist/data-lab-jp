from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_photo_rights_scope_audit as subject  # noqa: E402


class EbookPhotoRightsScopeAuditTests(unittest.TestCase):
    def test_reuse_candidates_do_not_confirm_exact_scope(self):
        result = subject.assess()
        self.assertEqual(result.status, subject.READY)
        self.assertIn("title", result.reuse_candidate_fields)
        self.assertIn("image", result.reuse_candidate_fields)
        self.assertIn("actresses", result.scope_review_required_fields)
        self.assertIn("authors", result.scope_review_required_fields)
        self.assertIn("manufactures", result.scope_review_required_fields)
        self.assertIn("product_description", result.prohibited_fields)
        self.assertFalse(result.exact_ebook_photo_scope_confirmed)
        self.assertFalse(result.contributor_semantics_confirmed)
        self.assertFalse(result.image_scope_confirmed)
        self.assertFalse(result.field_rights_confirmed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.gate_change_allowed)

    def test_policy_drift_fails_closed(self):
        with mock.patch.object(subject.rights, "validate_policy", return_value=("DRIFT",)):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)

    def test_nonapproved_candidate_mapping_fails_closed(self):
        changed = mock.Mock(
            public_display=subject.rights.PROHIBITED,
            evidence_type=subject.rights.DIRECT_SUPPORT_CONFIRMATION,
            future_public_data_candidate=False,
        )
        with mock.patch.object(subject.rights, "decision_for", return_value=changed):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)

    def test_prohibited_field_policy_drift_fails_closed(self):
        original = subject.rights.decision_for

        def changed(field):
            decision = original(field)
            if field == "product_description":
                return mock.Mock(public_display=subject.rights.APPROVED)
            return decision

        with mock.patch.object(subject.rights, "decision_for", side_effect=changed):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
