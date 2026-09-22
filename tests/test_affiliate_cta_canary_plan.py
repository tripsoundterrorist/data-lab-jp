from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canary_plan as plan
import revenue_mvp_current_state as current_state


class AffiliateCtaCanaryPlanTests(unittest.TestCase):
    def setUp(self):
        self.current = current_state.current_state()
        self.assertEqual(self.current.status, current_state.LIVE_AFFILIATE_CLOSED)

    def test_exact_closed_state_produces_review_only_plan(self):
        result = plan.assess(self.current)
        self.assertEqual(result.status, plan.READY)
        self.assertEqual(result.proposed_item_limit, 10)
        self.assertEqual(result.cta_label, "公式商品ページを見る（外部サイト）")
        self.assertTrue(result.disclosure_text.startswith("PR："))
        self.assertTrue(result.compliance_approval_required)
        self.assertTrue(result.user_activation_approval_required)
        self.assertFalse(result.cta_activation_allowed)
        self.assertFalse(result.d1_write_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertFalse(result.paid_plan_change_allowed)

    def test_limit_is_bounded(self):
        for value in (0, 11, True, "10", None):
            with self.subTest(value=value):
                self.assertEqual(plan.assess(self.current, value).status, plan.BLOCKED)

    def test_unexpected_open_state_fails_closed(self):
        changed = replace(self.current, cta_allowed=True)
        result = plan.assess(changed)
        self.assertEqual(result.status, plan.BLOCKED)
        self.assertFalse(result.cta_activation_allowed)

    def test_stop_conditions_cover_content_disclosure_and_edge(self):
        result = plan.assess(self.current)
        self.assertIn("EDGE_ARTIFACT_MISMATCH", result.stop_conditions)
        self.assertIn("PR_DISCLOSURE_MISSING_OR_NOT_PROXIMATE", result.stop_conditions)
        self.assertIn("AFFILIATE_ELIGIBILITY_UNVERIFIED", result.stop_conditions)


if __name__ == "__main__":
    unittest.main()

