from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_funnel_review as subject  # noqa: E402


def payload():
    return {
        "version": "0.1",
        "period_start": "2026-10-01",
        "period_end": "2026-10-07",
        "ga4_processing_complete": True,
        "rows": [
            {
                "item_id": "itm_111111111111111111111111",
                "surface": "product_card",
                "outbound_product_clicks": 2,
            },
            {
                "item_id": "itm_222222222222222222222222",
                "surface": "product_card",
                "outbound_product_clicks": 5,
            },
        ],
    }


class ProductFunnelReviewTests(unittest.TestCase):
    def test_valid_rows_are_ranked_without_automatic_action(self):
        result = subject.build_review(payload())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.total_outbound_product_clicks, 7)
        self.assertEqual(result.observed_product_count, 2)
        self.assertEqual(
            result.ranked_products[0]["item_id"],
            "itm_222222222222222222222222",
        )
        self.assertEqual(result.disposition, "ADDITIONAL_CONFIRMATION_REQUIRED")
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.external_write_performed)

    def test_processing_window_waits_without_treating_missing_as_zero(self):
        value = payload()
        value["ga4_processing_complete"] = False
        value["rows"] = []
        result = subject.build_review(value)
        self.assertEqual(result.status, subject.WAITING)
        self.assertIsNone(result.total_outbound_product_clicks)
        self.assertIn("GA4_PROCESSING_WINDOW_NOT_COMPLETE", result.reason_codes)

    def test_processed_empty_period_is_explicit_zero(self):
        value = payload()
        value["rows"] = []
        result = subject.build_review(value)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.total_outbound_product_clicks, 0)
        self.assertIn("NO_OBSERVED_CLICKS", result.reason_codes)

    def test_invalid_unknown_duplicate_and_unprocessed_rows_fail_closed(self):
        cases = []
        unknown = payload(); unknown["extra"] = True; cases.append(unknown)
        bad_id = payload(); bad_id["rows"][0]["item_id"] = "unsafe"; cases.append(bad_id)
        bad_surface = payload(); bad_surface["rows"][0]["surface"] = "unknown"; cases.append(bad_surface)
        negative = payload(); negative["rows"][0]["outbound_product_clicks"] = -1; cases.append(negative)
        duplicate = payload(); duplicate["rows"].append(deepcopy(duplicate["rows"][0])); cases.append(duplicate)
        pending = payload(); pending["ga4_processing_complete"] = False; cases.append(pending)
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(subject.build_review(value).status, subject.BLOCKED)

    def test_period_is_bounded(self):
        for start, end in (("2026-10-08", "2026-10-01"), ("2026-10-01", "2026-11-02")):
            value = payload(); value["period_start"] = start; value["period_end"] = end
            with self.subTest(start=start, end=end):
                self.assertEqual(subject.build_review(value).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
