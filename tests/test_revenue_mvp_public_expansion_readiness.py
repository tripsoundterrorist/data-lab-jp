from datetime import datetime, timedelta, timezone
import hashlib
import json
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
        "candidate_render_performance_verified": False,
        "cloudflare_free_plan_capacity_verified": False,
        "compliance_publication_confirmed": False,
        "product_funnel_window_closed": False,
        "product_funnel_review_completed": False,
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
        self.assertEqual(current.affiliate_redirect_ready_count, 300)
        self.assertEqual(current.runtime_revalidation_ready_count, 300)
        self.assertTrue(current.sitemap_capacity_verified)
        self.assertTrue(current.rollback_plan_verified)
        self.assertTrue(current.seo_quality_reviewed)
        self.assertTrue(current.candidate_render_performance_verified)
        self.assertNotIn("SITEMAP_CAPACITY_UNVERIFIED", result.reason_codes)
        self.assertNotIn("ROLLBACK_PLAN_UNVERIFIED", result.reason_codes)
        self.assertNotIn("SEO_QUALITY_UNREVIEWED", result.reason_codes)
        self.assertNotIn("CANDIDATE_RENDER_PERFORMANCE_UNVERIFIED", result.reason_codes)
        self.assertNotIn("AFFILIATE_REDIRECT_NOT_EXACT", result.reason_codes)
        self.assertNotIn("RUNTIME_REVALIDATION_NOT_EXACT", result.reason_codes)
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

    def test_invalid_seo_quality_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            with mock.patch.object(subject, "SEO_QUALITY_EVIDENCE", invalid):
                current = subject.current_evidence()
            self.assertFalse(current.seo_quality_reviewed)

    def test_invalid_render_performance_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            with mock.patch.object(subject, "RENDER_PERFORMANCE_EVIDENCE", invalid):
                current = subject.current_evidence()
            self.assertFalse(current.candidate_render_performance_verified)

    def test_missing_cloudflare_observation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with mock.patch.object(subject, "CLOUDFLARE_CAPACITY_EVIDENCE", missing):
                current = subject.current_evidence()
            self.assertFalse(current.cloudflare_free_plan_capacity_verified)

    def test_current_valid_cloudflare_observation_is_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            observation = Path(directory) / "cloudflare.json"
            observation.write_text(json.dumps({
                "version": "0.1",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "workers_requests_24h": 1,
                "workers_cpu_limit_errors_24h": 0,
                "d1_rows_read_24h": 1,
                "d1_rows_written_24h": 1,
                "d1_database_storage_bytes": 1,
                "d1_account_storage_bytes": 1,
                "active_cron_triggers": [],
            }), encoding="utf-8")
            with mock.patch.object(
                subject, "CLOUDFLARE_CAPACITY_EVIDENCE", observation
            ):
                current = subject.current_evidence()
            self.assertTrue(current.cloudflare_free_plan_capacity_verified)

    def test_stale_cloudflare_observation_is_rejected_at_read_time(self):
        with tempfile.TemporaryDirectory() as directory:
            observation = Path(directory) / "cloudflare.json"
            observation.write_text(json.dumps({
                "version": "0.1",
                "observed_at": (
                    datetime.now(timezone.utc) - timedelta(days=2)
                ).isoformat(),
                "workers_requests_24h": 1,
                "workers_cpu_limit_errors_24h": 0,
                "d1_rows_read_24h": 1,
                "d1_rows_written_24h": 1,
                "d1_database_storage_bytes": 1,
                "d1_account_storage_bytes": 1,
                "active_cron_triggers": [],
            }), encoding="utf-8")
            with mock.patch.object(
                subject, "CLOUDFLARE_CAPACITY_EVIDENCE", observation
            ):
                current = subject.current_evidence()
            self.assertFalse(current.cloudflare_free_plan_capacity_verified)

    def test_current_compliance_and_funnel_evidence_remain_unconfirmed(self):
        current = subject.current_evidence()
        self.assertFalse(current.compliance_publication_confirmed)
        self.assertFalse(current.product_funnel_window_closed)
        self.assertFalse(current.product_funnel_review_completed)

    def test_completed_aggregate_funnel_review_is_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "funnel-review.json"
            receipt.write_text(json.dumps({
                "version": "0.1",
                "status": "PRODUCT_FUNNEL_REVIEW_COMPLETED",
                "period_start": "2026-10-02",
                "period_end": "2026-10-08",
                "product_funnel_review_completed": True,
                "total_outbound_product_clicks": 0,
                "observed_product_count": 0,
                "zero_click_period_confirmed": True,
                "expansion_decision_allowed": False,
                "production_write_allowed": False,
                "external_write_performed": False,
                "reason_codes": [],
            }), encoding="utf-8")
            with mock.patch.object(subject, "FUNNEL_REVIEW_EVIDENCE", receipt):
                current = subject.current_evidence()
            self.assertTrue(current.product_funnel_review_completed)

    def test_invalid_external_evidence_cannot_self_authorize_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cloudflare = root / "cloudflare.json"
            cloudflare.write_text("{}", encoding="utf-8")
            funnel = root / "funnel.json"
            funnel.write_text("{}", encoding="utf-8")
            with (
                mock.patch.object(subject, "CLOUDFLARE_CAPACITY_EVIDENCE", cloudflare),
                mock.patch.object(subject, "FUNNEL_WINDOW_EVIDENCE", funnel),
            ):
                current = subject.current_evidence()
            self.assertFalse(current.cloudflare_free_plan_capacity_verified)
            self.assertFalse(current.compliance_publication_confirmed)
            self.assertFalse(current.product_funnel_window_closed)
            self.assertFalse(current.product_funnel_review_completed)

    def test_compliance_remains_false_without_separate_decision_receipt(self):
        current = subject.current_evidence()
        self.assertFalse(current.compliance_publication_confirmed)

    def test_only_hash_pinned_ready_packet_and_explicit_receipt_confirm_compliance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / "packet.json"
            packet_value = {
                "version": "0.1",
                "status": "READY_FOR_MANUAL_COMPLIANCE_DECISION",
                "target_item_count": 300,
                "official_lifecycle_core_confirmed": True,
                "candidate_lookup_ready_count": 300,
                "candidate_redirect_ready_count": 300,
                "candidate_runtime_ready_count": 300,
                "presentation_policy_verified": True,
                "product_funnel_window_closed": True,
                "product_funnel_review_completed": True,
                "compliance_publication_confirmed": False,
                "publication_allowed": False,
                "production_write_allowed": False,
                "reason_codes": [],
                "required_manual_checks": [],
            }
            packet.write_bytes(json.dumps(
                packet_value, ensure_ascii=False, sort_keys=True
            ).encode("utf-8"))
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "version": "0.1",
                "decision": "CONFIRM_EXPANSION_COMPLIANCE",
                "decided_at": "2026-10-10T12:00:00+09:00",
                "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
                "reviewer_role": "DATA_LAB_OWNER",
            }), encoding="utf-8")
            with (
                mock.patch.object(subject, "COMPLIANCE_PACKET_EVIDENCE", packet),
                mock.patch.object(subject, "COMPLIANCE_DECISION_RECEIPT", receipt),
            ):
                current = subject.current_evidence()
            self.assertTrue(current.compliance_publication_confirmed)

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
            "candidate_render_performance_verified": True,
            "cloudflare_free_plan_capacity_verified": True,
            "compliance_publication_confirmed": True,
            "product_funnel_window_closed": True,
            "product_funnel_review_completed": True,
            "rollback_plan_verified": True,
        }
        values.update(changes)
        return evidence(**values)


if __name__ == "__main__":
    unittest.main()
