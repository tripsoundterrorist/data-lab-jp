import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "x-manual-post-candidate-20260930.json"


class XManualPostCandidateEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_candidate_remains_manual_and_fail_closed(self):
        self.assertEqual(self.evidence["status"], "POSTED_WITH_TEXT_VARIATION")
        validation = self.evidence["validation"]
        self.assertTrue(validation["pr_disclosure_present"])
        self.assertFalse(validation["product_media_used"])
        self.assertFalse(validation["direct_affiliate_link_used"])
        self.assertFalse(validation["automatic_posting_authorized"])
        self.assertFalse(self.evidence["external_write_performed"])

    def test_candidate_is_bounded_and_measurable(self):
        validation = self.evidence["validation"]
        self.assertLessEqual(validation["non_url_raw_characters"], 140)
        self.assertLessEqual(
            validation["x_weighted_length_estimate"],
            validation["x_weighted_limit"],
        )
        self.assertEqual(validation["verified_public_item_count"], 100)
        self.assertIn("utm_source=x", self.evidence["post_text"])
        self.assertIn("【PR】", self.evidence["post_text"])
        measurement = self.evidence["measurement_after_manual_post"]
        self.assertEqual(measurement["public_views_at_first_observation"], 3)
        self.assertFalse(measurement["text_matches_candidate"])
        self.assertEqual(measurement["text_variation"], "UNINTENDED_PREFIX_PRESENT")
        for key in (
            "impressions",
            "link_clicks",
            "ga4_sessions",
            "ga4_outbound_product_clicks",
            "dmm_click_delta",
            "affiliate_conversions",
            "affiliate_revenue_yen",
        ):
            self.assertEqual(measurement[key], "NOT_ACQUIRED")

    def test_early_funnel_observation_does_not_infer_results(self):
        observation = json.loads(
            (
                ROOT
                / "docs"
                / "evidence"
                / "revenue-mvp-x-post-early-funnel-observation-20261001.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(observation["status"], "EARLY_OBSERVATION_NO_SIGNAL_YET")
        self.assertEqual(observation["ga4"]["realtime_active_users_last_30_minutes"], 0)
        self.assertEqual(observation["dmm_affiliate"]["status"], "NO_DATA")
        self.assertEqual(observation["ga4"]["campaign_attribution"], "NOT_ACQUIRED")
        self.assertEqual(observation["dmm_affiliate"]["revenue_increment_yen"], "NOT_ACQUIRED")
        self.assertTrue(observation["site_follow_up"]["stale_prepublication_copy_detected"])
        self.assertFalse(observation["site_follow_up"]["change_applied"])
        self.assertFalse(observation["external_write_performed"])


if __name__ == "__main__":
    unittest.main()
