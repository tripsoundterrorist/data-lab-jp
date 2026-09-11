from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_presentation as cta  # noqa: E402
import product_lifecycle as lifecycle  # noqa: E402
import revenue_mvp_official_answer_matrix as matrix  # noqa: E402
import rights_decision_policy as rights  # noqa: E402


class RevenueMvpOfficialResponseConditionTests(unittest.TestCase):
    def test_api_image_scope_is_narrower_than_official_allowance(self):
        self.assertEqual(
            rights.decision_for("product_main_image").public_display,
            rights.APPROVED,
        )
        for field in (
            "dmm_books_product_image",
            "product_description",
            "user_review_text",
            "actress_api_face_image",
            "person_list_image",
            "sample_video",
            "video_capture",
        ):
            with self.subTest(field=field):
                self.assertEqual(
                    rights.decision_for(field).public_display,
                    rights.PROHIBITED,
                )
        self.assertTrue(matrix.current_entries()["API_IMAGE_USE"].conditions_verified)

    def test_explicit_unavailable_item_is_never_publication_eligible(self):
        as_of = datetime(2026, 9, 8, tzinfo=timezone.utc)
        result = lifecycle.evaluate_product_lifecycle(
            last_observed_at="2026-09-08T00:00:00Z",
            verification={
                "verification_source": "AVAILABILITY_VERIFIER",
                "verified_at": "2026-09-08T00:00:00Z",
                "verification_result": "unavailable",
                "verification_reason": "EXPLICIT_CHECK",
                "source_status_code": None,
            },
            as_of=as_of,
            policy=lifecycle.LifecyclePolicy(
                observation_recency_window=timedelta(days=2),
                verification_ttl=timedelta(days=3),
            ),
        )
        self.assertEqual(result.state, lifecycle.LifecycleState.CONFIRMED_UNAVAILABLE)
        self.assertFalse(result.lifecycle_eligible_for_publication)
        self.assertTrue(
            matrix.current_entries()["DISCONTINUED_ITEM_HANDLING"].conditions_verified
        )

    def test_independent_metric_disclosure_is_explicit(self):
        disclosure = (ROOT / "disclosure.html").read_text(encoding="utf-8")
        self.assertIn("DATA LAB独自の集計", disclosure)
        self.assertIn("DMM/FANZA公式の評価・順位ではありません", disclosure)
        self.assertIn("算出対象、基準時刻、データ出典、主な制約", disclosure)
        self.assertTrue(
            matrix.current_entries()["OFFICIAL_RANKING_CONFUSION"].conditions_verified
        )

    def test_affiliate_cta_requires_proximate_pr_disclosure(self):
        self.assertTrue(cta.DISCLOSURE_TEXT.startswith("PR："))
        self.assertIn("アフィリエイトリンク", cta.DISCLOSURE_TEXT)
        self.assertIn("報酬を受け取ることがあります", cta.DISCLOSURE_TEXT)
        self.assertTrue(
            matrix.current_entries()["PR_AD_AFFILIATE_DISCLOSURE"].conditions_verified
        )

    def test_sns_conditions_remain_blocking_after_domain_confirmation(self):
        result = matrix.assess_answer_matrix(matrix.current_entries())
        self.assertTrue(result.core_publication_candidate)
        self.assertFalse(result.sns_operation_candidate)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertEqual(
            result.blocking_topic_ids,
            (
                "SNS_TO_SITE_TO_FANZA_FUNNEL",
                "SNS_ACCOUNT_REGISTRATION",
                "SNS_PRODUCT_MEDIA_USE",
                "AUTOMATED_FACT_POSTING",
            ),
        )


if __name__ == "__main__":
    unittest.main()
