from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_public_expansion_readiness as subject  # noqa: E402


def evidence(**changes):
    values = {
        "current_public_item_count": 100,
        "target_public_item_count": 300,
        "candidate_unique_item_count": 0,
        "eligible_item_count": 0,
        "image_ready_count": 0,
        "price_ready_count": 0,
        "fresh_item_count": 0,
        "affiliate_lookup_ready_count": 0,
        "affiliate_redirect_ready_count": 0,
        "runtime_revalidation_ready_count": 0,
        "existing_surface_preservation_verified": False,
        "sitemap_capacity_verified": False,
        "seo_quality_reviewed": False,
        "cloudflare_free_plan_capacity_verified": False,
        "compliance_publication_confirmed": False,
        "product_funnel_window_closed": False,
        "rollback_plan_verified": False,
    }
    values.update(changes)
    return subject.ExpansionEvidence(**values)


class PublicExpansionReadinessTests(unittest.TestCase):
    def test_current_state_is_blocked_without_publication_or_writes(self):
        current = subject.current_evidence()
        result = subject.assess(current)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.manual_expansion_review_candidate)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertNotIn("CANDIDATE_SET_NOT_EXACT", result.reason_codes)
        self.assertNotIn("ELIGIBILITY_NOT_EXACT", result.reason_codes)
        self.assertNotIn("IMAGE_COVERAGE_NOT_EXACT", result.reason_codes)
        self.assertNotIn("PRICE_COVERAGE_NOT_EXACT", result.reason_codes)
        self.assertNotIn("FRESHNESS_NOT_EXACT", result.reason_codes)
        self.assertNotIn("AFFILIATE_LOOKUP_NOT_EXACT", result.reason_codes)
        self.assertEqual(current.affiliate_lookup_ready_count, 300)
        self.assertEqual(current.affiliate_redirect_ready_count, 124)
        self.assertEqual(current.runtime_revalidation_ready_count, 49)
        self.assertTrue(current.sitemap_capacity_verified)
        self.assertTrue(current.rollback_plan_verified)
        self.assertNotIn("SITEMAP_CAPACITY_UNVERIFIED", result.reason_codes)
        self.assertNotIn("ROLLBACK_PLAN_UNVERIFIED", result.reason_codes)
        self.assertIn("AFFILIATE_REDIRECT_NOT_EXACT", result.reason_codes)
        self.assertIn("COMPLIANCE_PUBLICATION_UNCONFIRMED", result.reason_codes)

    def test_missing_or_invalid_collection_evidence_fails_closed_to_zero_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with mock.patch.object(subject, "COLLECTION_EVIDENCE", missing):
                current = subject.current_evidence()
            self.assertEqual(current.candidate_unique_item_count, 0)
            self.assertFalse(current.existing_surface_preservation_verified)
            missing.write_text("{}", encoding="utf-8")
            with mock.patch.object(subject, "COLLECTION_EVIDENCE", missing):
                current = subject.current_evidence()
            self.assertEqual(current.fresh_item_count, 0)

    def test_invalid_d1_evidence_fails_closed_to_zero_runtime_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            with mock.patch.object(subject, "D1_COVERAGE_EVIDENCE", invalid):
                current = subject.current_evidence()
            self.assertEqual(current.affiliate_lookup_ready_count, 0)
            self.assertEqual(current.affiliate_redirect_ready_count, 0)
            self.assertEqual(current.runtime_revalidation_ready_count, 0)

    def test_invalid_sitemap_capacity_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            with mock.patch.object(subject, "SITEMAP_CAPACITY_EVIDENCE", invalid):
                current = subject.current_evidence()
            self.assertFalse(current.sitemap_capacity_verified)

    def test_invalid_rollback_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            with mock.patch.object(subject, "ROLLBACK_EVIDENCE", invalid):
                current = subject.current_evidence()
            self.assertFalse(current.rollback_plan_verified)

    def test_only_the_next_300_item_stage_is_accepted(self):
        result = subject.assess(evidence(target_public_item_count=500))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("TARGET_STAGE_INVALID", result.reason_codes)

    def test_local_inventory_does_not_prove_exact_candidate_or_eligibility(self):
        result = subject.assess(evidence(candidate_unique_item_count=1109))
        self.assertIn("CANDIDATE_SET_NOT_EXACT", result.reason_codes)
        self.assertIn("ELIGIBILITY_NOT_EXACT", result.reason_codes)

    def test_any_candidate_coverage_mismatch_blocks(self):
        complete = self.complete_evidence(image_ready_count=299)
        result = subject.assess(complete)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("IMAGE_COVERAGE_NOT_EXACT", result.reason_codes)

    def test_complete_evidence_reaches_manual_review_only(self):
        result = subject.assess(self.complete_evidence())
        self.assertEqual(result.status, subject.READY_FOR_MANUAL_EXPANSION_REVIEW)
        self.assertTrue(result.manual_expansion_review_candidate)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertEqual(result.reason_codes, ())

    def test_invalid_input_fails_closed(self):
        self.assertEqual(subject.assess({}).status, subject.FAIL_CLOSED)
        self.assertEqual(
            subject.assess(evidence(candidate_unique_item_count=True)).status,
            subject.FAIL_CLOSED,
        )

    def test_reason_codes_are_deterministic(self):
        result = subject.assess(subject.current_evidence())
        self.assertEqual(result.reason_codes, tuple(sorted(result.reason_codes)))

    @staticmethod
    def complete_evidence(**changes):
        values = {
            "candidate_unique_item_count": 300,
            "eligible_item_count": 300,
            "image_ready_count": 300,
            "price_ready_count": 300,
            "fresh_item_count": 300,
            "affiliate_lookup_ready_count": 300,
            "affiliate_redirect_ready_count": 300,
            "runtime_revalidation_ready_count": 300,
            "existing_surface_preservation_verified": True,
            "sitemap_capacity_verified": True,
            "seo_quality_reviewed": True,
            "cloudflare_free_plan_capacity_verified": True,
            "compliance_publication_confirmed": True,
            "product_funnel_window_closed": True,
            "rollback_plan_verified": True,
        }
        values.update(changes)
        return evidence(**values)


if __name__ == "__main__":
    unittest.main()
