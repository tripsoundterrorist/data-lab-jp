import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_compliance_packet as subject  # noqa: E402


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ExpansionCompliancePacketTests(unittest.TestCase):
    def setUp(self):
        self.official = load(subject.OFFICIAL_RESPONSE)
        self.coverage = load(subject.COVERAGE_EVIDENCE)
        self.seo = load(subject.SEO_EVIDENCE)
        self.funnel = load(subject.FUNNEL_EVIDENCE)
        self.funnel_review = {}

    def test_current_packet_is_blocked_without_authorizing_anything(self):
        result = subject.build_packet(
            self.official, self.coverage, self.seo, self.funnel, self.funnel_review
        )
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertTrue(result.official_lifecycle_core_confirmed)
        self.assertEqual(result.candidate_lookup_ready_count, 300)
        self.assertEqual(result.candidate_redirect_ready_count, 300)
        self.assertEqual(result.candidate_runtime_ready_count, 300)
        self.assertTrue(result.presentation_policy_verified)
        self.assertFalse(result.product_funnel_window_closed)
        self.assertFalse(result.product_funnel_review_completed)
        self.assertFalse(result.compliance_publication_confirmed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertNotIn("RUNTIME_ELIGIBILITY_INCOMPLETE", result.reason_codes)
        self.assertIn("PRODUCT_FUNNEL_WINDOW_OPEN", result.reason_codes)

    def test_complete_aggregate_evidence_reaches_manual_decision_only(self):
        coverage = dict(self.coverage)
        coverage["candidate_redirect_ready_count"] = 300
        coverage["candidate_runtime_revalidation_ready_count"] = 300
        funnel = dict(self.funnel)
        funnel["product_funnel_window_closed"] = True
        funnel_review = {
            "status": "PRODUCT_FUNNEL_REVIEW_COMPLETED",
            "period_start": "2026-10-02",
            "period_end": "2026-10-08",
            "product_funnel_review_completed": True,
            "expansion_decision_allowed": False,
            "production_write_allowed": False,
            "external_write_performed": False,
            "reason_codes": [],
        }
        result = subject.build_packet(
            self.official, coverage, self.seo, funnel, funnel_review
        )
        self.assertEqual(result.status, subject.READY)
        self.assertFalse(result.compliance_publication_confirmed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_missing_official_confirmation_blocks(self):
        official = json.loads(json.dumps(self.official))
        lifecycle = next(
            value for value in official
            if value["referenced_blocker"] == "DMM_LIFECYCLE_AVAILABILITY"
        )
        lifecycle["explicit_confirmations"].remove("NONVISIBLE_LINK_HANDLING")
        result = subject.build_packet(
            official, self.coverage, self.seo, self.funnel, self.funnel_review
        )
        self.assertIn("OFFICIAL_LIFECYCLE_CORE_UNCONFIRMED", result.reason_codes)

    def test_malformed_evidence_fails_closed(self):
        result = subject.build_packet(
            None, self.coverage, self.seo, self.funnel, self.funnel_review
        )
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
