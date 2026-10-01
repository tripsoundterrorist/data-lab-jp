from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_funnel_review_receipt as subject  # noqa: E402


def payload(rows=None):
    return {
        "version": "0.1",
        "period_start": "2026-10-02",
        "period_end": "2026-10-08",
        "ga4_processing_complete": True,
        "rows": [] if rows is None else rows,
    }


class ProductFunnelReviewReceiptTests(unittest.TestCase):
    def test_exact_processed_period_creates_aggregate_receipt_only(self):
        result = subject.build(payload([{
            "item_id": "itm_111111111111111111111111",
            "surface": "product_card",
            "outbound_product_clicks": 3,
        }]))
        self.assertEqual(result.status, subject.COMPLETED)
        self.assertTrue(result.product_funnel_review_completed)
        self.assertEqual(result.total_outbound_product_clicks, 3)
        self.assertEqual(result.observed_product_count, 1)
        self.assertFalse(result.zero_click_period_confirmed)
        self.assertFalse(result.expansion_decision_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertNotIn("item_id", result.to_dict())

    def test_processed_zero_is_explicit_not_missing(self):
        result = subject.build(payload())
        self.assertTrue(result.product_funnel_review_completed)
        self.assertEqual(result.total_outbound_product_clicks, 0)
        self.assertTrue(result.zero_click_period_confirmed)

    def test_wrong_period_pending_or_malformed_input_blocks(self):
        wrong = payload(); wrong["period_start"] = "2026-10-01"
        pending = payload(); pending["ga4_processing_complete"] = False
        for value in (wrong, pending, None):
            with self.subTest(value=value):
                result = subject.build(value)
                self.assertEqual(result.status, subject.BLOCKED)
                self.assertFalse(result.product_funnel_review_completed)
                self.assertIsNone(result.total_outbound_product_clicks)


if __name__ == "__main__":
    unittest.main()
