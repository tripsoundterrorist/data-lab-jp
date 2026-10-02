from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_rights_scope_audit as subject  # noqa: E402


class DoujinRightsScopeAuditTests(unittest.TestCase):
    def test_reuses_only_explicitly_approved_existing_mappings(self):
        result = subject.assess()
        self.assertEqual(result.status, subject.READY)
        self.assertIn("title", result.direct_approved_fields)
        self.assertIn("discount_rate", result.derived_condition_fields)
        self.assertIn("release_date_raw", result.scope_review_required_fields)
        self.assertFalse(result.field_rights_confirmed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.gate_change_allowed)

    def test_policy_drift_fails_closed(self):
        with mock.patch.object(subject.rights, "validate_policy", return_value=("DRIFT",)):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)

    def test_nonapproved_mapping_fails_closed(self):
        changed = mock.Mock(
            public_display=subject.rights.PROHIBITED,
            evidence_type=subject.rights.DIRECT_SUPPORT_CONFIRMATION,
            future_public_data_candidate=False,
        )
        with mock.patch.object(subject.rights, "decision_for", return_value=changed):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
