import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_current_state as current_state  # noqa: E402


class MonetizationStartEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads(
            (ROOT / "docs" / "evidence" / "revenue-mvp-monetization-start-20260930.json")
            .read_text(encoding="utf-8")
        )

    def test_evidence_matches_current_live_surface(self):
        state = current_state.current_state()
        surface = self.evidence["public_surface"]
        runtime = self.evidence["affiliate_runtime"]
        self.assertEqual(self.evidence["status"], "MONETIZATION_STARTED")
        self.assertEqual(state.status, current_state.PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE)
        self.assertEqual(surface["artifact_sha256"], current_state.REFRESHED_PRODUCT_CARD_SHA256)
        self.assertEqual(surface["item_count"], state.live_item_count)
        self.assertEqual(surface["cta_count"], 100)
        self.assertEqual(runtime["runtime_redirect_matches"], 100)
        self.assertEqual(runtime["representative_redirects_passed"], 3)
        self.assertFalse(runtime["private_affiliate_url_exposed"])

    def test_unobserved_results_are_not_invented(self):
        measurement = self.evidence["measurement"]
        self.assertTrue(measurement["consent_first_funnel_events_deployed"])
        baseline_path = ROOT / measurement["ga4_baseline_evidence"]
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        self.assertEqual(baseline["status"], "BASELINE_OBSERVED")
        self.assertEqual(baseline["summary"]["sessions"], 8)
        self.assertIn("post_monetization_start_sessions", baseline["not_acquired"])
        self.assertFalse(baseline["external_write_performed"])
        link_path = ROOT / baseline["search_console_link_evidence"]
        link = json.loads(link_path.read_text(encoding="utf-8"))
        self.assertEqual(link["status"], "LINK_VERIFIED")
        self.assertEqual(link["search_console_property"], "datalabx.jp")
        self.assertEqual(link["property_type"], "DOMAIN")
        self.assertTrue(link["identifiers_redacted"])
        self.assertTrue(link["created_by_user"])
        self.assertFalse(link["external_write_performed_by_agent"])
        affiliate_path = ROOT / measurement["dmm_affiliate_baseline_evidence"]
        affiliate = json.loads(affiliate_path.read_text(encoding="utf-8"))
        self.assertEqual(affiliate["status"], "BASELINE_OBSERVED")
        self.assertEqual(affiliate["summary"]["clicks"], 1)
        self.assertEqual(affiliate["summary"]["total_reward_count"], 0)
        self.assertEqual(affiliate["summary"]["total_reward_yen"], 0)
        self.assertTrue(affiliate["identifiers_redacted"])
        self.assertFalse(affiliate["external_write_performed"])
        for key in (
            "observed_sessions",
            "observed_outbound_product_clicks",
            "observed_affiliate_conversions",
            "observed_revenue",
        ):
            self.assertEqual(measurement[key], "NOT_ACQUIRED")

    def test_scope_expansion_and_paid_changes_remain_closed(self):
        self.assertFalse(self.evidence["operations"]["paid_plan_change"])
        self.assertEqual(self.evidence["boundaries"]["global_publication_gate"], "unchanged")
        self.assertFalse(self.evidence["boundaries"]["automatic_x_posting"])
        self.assertFalse(self.evidence["boundaries"]["unreviewed_scope_expansion"])

    def test_funnel_readiness_audit_preserves_observation_only_boundary(self):
        audit = json.loads(
            (ROOT / "docs" / "evidence" / "revenue-mvp-funnel-readiness-audit-20260930.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(audit["status"], "FUNNEL_READY_FOR_OBSERVATION")
        self.assertEqual(audit["current_state"]["live_item_count"], 100)
        self.assertEqual(audit["current_state"]["affiliate_d1_enabled_row_count"], 100)
        self.assertTrue(all(audit["funnel_checks"].values()))
        self.assertEqual(audit["changes_required_now"], [])
        self.assertEqual(audit["deferred"][0]["topic"], "public_ranking_numbers")
        self.assertFalse(audit["production_write_performed"])
        self.assertFalse(audit["external_write_performed"])


if __name__ == "__main__":
    unittest.main()
