from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_prior_evidence_reuse_audit as subject  # noqa: E402


class DoujinPriorEvidenceReuseAuditTests(unittest.TestCase):
    def test_routes_all_questions_without_auto_resolution(self):
        result = subject.assess()
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(len(result.scope_review_candidate_ids), 7)
        self.assertEqual(len(result.recontact_required_ids), 5)
        self.assertEqual(len(result.internal_review_ids), 2)
        self.assertEqual(result.resolved_without_review_ids, ())
        self.assertFalse(result.external_send_performed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)

    def test_private_retention_scope_is_not_inferred(self):
        result = subject.assess()
        self.assertEqual(
            set(result.retention_scope_ambiguity_ids),
            set(subject.RETENTION_SCOPE_AMBIGUITY),
        )
        self.assertTrue(set(subject.RETENTION_SCOPE_AMBIGUITY) <= set(result.recontact_required_ids))

    def test_policy_drift_fails_closed(self):
        with mock.patch.object(subject.rights, "validate_policy", return_value=("DRIFT",)):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.scope_review_candidate_ids, ())

    def test_link_evidence_drift_fails_closed(self):
        with mock.patch.object(subject.cta_policy, "OFFICIAL_STATUS", "UNKNOWN"):
            result = subject.assess()
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
