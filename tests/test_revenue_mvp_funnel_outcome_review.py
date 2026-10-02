from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_funnel_outcome_review as subject  # noqa: E402


def payload(clicks=4, conversions=1, revenue_yen=500):
    return {
        "version": "0.1",
        "ga4_input": {
            "version": "0.1",
            "period_start": "2026-10-02",
            "period_end": "2026-10-08",
            "ga4_processing_complete": True,
            "rows": [{
                "item_id": "itm_000000000000000000000001",
                "surface": "product_card",
                "outbound_product_clicks": clicks,
            }],
        },
        "dmm_input": {
            "version": "0.1",
            "period_start": "2026-10-02",
            "period_end": "2026-10-08",
            "report_status": "DATA_ACQUIRED",
            "affiliate_conversions": conversions,
            "affiliate_revenue_yen": revenue_yen,
        },
    }


class FunnelOutcomeReviewTests(unittest.TestCase):
    def test_complete_inputs_produce_only_same_period_proxies(self):
        result = subject.build_review(payload(), evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.same_period_conversion_click_ratio, 0.25)
        self.assertEqual(result.same_period_revenue_per_click_yen, 125.0)
        self.assertEqual(result.attribution_status, "NOT_ESTABLISHED_BY_AGGREGATES")
        self.assertIn(
            "SAME_PERIOD_AGGREGATES_NOT_USER_LEVEL_ATTRIBUTION", result.reason_codes
        )
        self.assertFalse(result.expansion_decision_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_pre_review_date_waits(self):
        result = subject.build_review(payload(), evaluated_on=date(2026, 10, 9))
        self.assertEqual(result.status, subject.WAITING)
        self.assertEqual(result.same_period_conversion_click_ratio, subject.NOT_ACQUIRED)

    def test_no_data_waits_and_is_not_zero(self):
        value = payload()
        value["dmm_input"].update({
            "report_status": "NO_DATA",
            "affiliate_conversions": "NOT_ACQUIRED",
            "affiliate_revenue_yen": "NOT_ACQUIRED",
        })
        result = subject.build_review(value, evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.status, subject.WAITING)
        self.assertIsNone(result.affiliate_conversions)

    def test_zero_click_denominator_does_not_create_rates(self):
        result = subject.build_review(
            payload(clicks=0, conversions=0, revenue_yen=0),
            evaluated_on=date(2026, 10, 10),
        )
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.same_period_conversion_click_ratio, subject.NOT_ACQUIRED)
        self.assertEqual(result.same_period_revenue_per_click_yen, subject.NOT_ACQUIRED)
        self.assertIn("ZERO_CLICK_DENOMINATOR", result.reason_codes)

    def test_invalid_nested_input_waits_without_leaking_rows(self):
        value = payload()
        value["ga4_input"]["rows"][0]["item_id"] = "private-id"
        result = subject.build_review(value, evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.status, subject.WAITING)
        self.assertIsNone(result.outbound_product_clicks)

    def test_unknown_root_field_fails_closed(self):
        value = deepcopy(payload())
        value["extra"] = True
        self.assertEqual(
            subject.build_review(value, evaluated_on=date(2026, 10, 10)).status,
            subject.BLOCKED,
        )


if __name__ == "__main__":
    unittest.main()
