from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_control_center_status as subject  # noqa: E402
from tests.revenue_mvp_historical_fixture import historical_state_fixture


class RevenueMvpControlCenterStatusTests(unittest.TestCase):
    def test_historical_live_status_preserves_scope_and_blocks_expansion(self):
        with mock.patch.object(subject.live_state,'current_state',return_value=historical_state_fixture()):
            result = subject.current_status()
        self.assertEqual(result.status, subject.ACTIVE)
        self.assertEqual(result.revenue_priority, "P0")
        self.assertTrue(result.limited_surface_live)
        self.assertEqual(result.live_item_count, 100)
        self.assertTrue(result.affiliate_cta_live)
        self.assertEqual(result.expansion_target_item_count, 300)
        self.assertEqual(result.expansion_lookup_ready_count, 300)
        self.assertEqual(result.expansion_redirect_ready_count, 300)
        self.assertEqual(result.expansion_runtime_ready_count, 300)
        self.assertFalse(result.next_batch_preparation_allowed)
        self.assertFalse(result.next_batch_live_execution_allowed)
        self.assertFalse(result.product_funnel_window_closed)
        self.assertFalse(result.product_funnel_review_completed)
        self.assertFalse(result.compliance_publication_confirmed)
        self.assertFalse(result.expansion_publication_allowed)
        self.assertFalse(result.ranking_implementation_review_candidate)
        self.assertFalse(result.production_write_allowed)
        self.assertNotIn(
            "CAPTURE_CURRENT_CLOUDFLARE_CAPACITY_AND_CRON_OBSERVATION",
            result.next_actions,
        )

    def test_inconsistent_component_fails_closed(self):
        with mock.patch.object(
            subject.activation_progress, "current_progress",
            return_value=subject.activation_progress._blocked("TEST"),
        ):
            result = subject.current_status()
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.limited_surface_live)
        self.assertFalse(result.production_write_allowed)

    def test_corrected_display_does_not_inherit_control_center_live_claim(self):
        historical=historical_state_fixture()
        pending=subject.live_state._failed('DISPLAY_REVIEW_REQUIRED')
        with mock.patch.object(subject.live_state,'current_state',return_value=pending):
            result=subject.current_status()
        self.assertEqual(result.status,subject.FAIL_CLOSED)
        self.assertFalse(result.limited_surface_live)
        self.assertFalse(result.affiliate_cta_live)
        self.assertFalse(result.production_write_allowed)
        self.assertTrue(historical.limited_surface_live)


if __name__ == "__main__":
    unittest.main()
