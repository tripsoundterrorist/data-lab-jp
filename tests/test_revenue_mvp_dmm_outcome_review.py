from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_dmm_outcome_review as subject  # noqa: E402


def payload():
    return {
        "version": "0.1",
        "period_start": "2026-10-02",
        "period_end": "2026-10-08",
        "report_status": subject.NOT_ACQUIRED,
        "affiliate_conversions": subject.NOT_ACQUIRED,
        "affiliate_revenue_yen": subject.NOT_ACQUIRED,
    }


class DmmOutcomeReviewTests(unittest.TestCase):
    def test_not_acquired_remains_waiting(self):
        result = subject.build_review(payload())
        self.assertEqual(result.status, subject.WAITING)
        self.assertIsNone(result.affiliate_conversions)
        self.assertIsNone(result.affiliate_revenue_yen)
        self.assertFalse(result.expansion_decision_allowed)

    def test_no_data_is_not_interpreted_as_zero(self):
        value = payload()
        value["report_status"] = subject.NO_DATA
        result = subject.build_review(value, evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.status, subject.WAITING)
        self.assertIn("DMM_REPORT_NO_DATA_NOT_ZERO", result.reason_codes)
        self.assertFalse(result.zero_conversion_period_confirmed)
        self.assertFalse(result.zero_revenue_period_confirmed)

    def test_acquired_zeroes_are_explicit(self):
        value = payload()
        value.update({
            "report_status": subject.DATA_ACQUIRED,
            "affiliate_conversions": 0,
            "affiliate_revenue_yen": 0,
        })
        result = subject.build_review(value, evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.zero_conversion_period_confirmed)
        self.assertTrue(result.zero_revenue_period_confirmed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.external_write_performed)

    def test_acquired_values_are_preserved(self):
        value = payload()
        value.update({
            "report_status": subject.DATA_ACQUIRED,
            "affiliate_conversions": 2,
            "affiliate_revenue_yen": 900,
        })
        result = subject.build_review(value, evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.affiliate_conversions, 2)
        self.assertEqual(result.affiliate_revenue_yen, 900)
        self.assertEqual(result.disposition, "ADDITIONAL_CONFIRMATION_REQUIRED")

    def test_acquired_values_wait_until_earliest_review_date(self):
        value = payload()
        value.update({
            "report_status": subject.DATA_ACQUIRED,
            "affiliate_conversions": 1,
            "affiliate_revenue_yen": 100,
        })
        result = subject.build_review(value, evaluated_on=date(2026, 10, 9))
        self.assertEqual(result.status, subject.WAITING)
        self.assertIn("EARLIEST_REVIEW_DATE_NOT_REACHED", result.reason_codes)
        self.assertIsNone(result.affiliate_conversions)
        self.assertIsNone(result.affiliate_revenue_yen)

    def test_non_exact_period_fails_closed(self):
        value = payload()
        value["period_start"] = "2026-10-01"
        result = subject.build_review(value, evaluated_on=date(2026, 10, 10))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("MEASUREMENT_PERIOD_NOT_EXACT", result.reason_codes)

    def test_unknown_fields_invalid_periods_and_negative_values_fail_closed(self):
        cases = []
        unknown = payload(); unknown["extra"] = 1; cases.append(unknown)
        invalid_period = payload(); invalid_period["period_end"] = "bad"; cases.append(invalid_period)
        negative = payload(); negative.update({
            "report_status": subject.DATA_ACQUIRED,
            "affiliate_conversions": -1,
            "affiliate_revenue_yen": 0,
        }); cases.append(negative)
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(subject.build_review(value).status, subject.BLOCKED)

    def test_unacquired_status_rejects_numeric_metrics(self):
        for report_status in (subject.NOT_ACQUIRED, subject.NO_DATA):
            value = deepcopy(payload())
            value["report_status"] = report_status
            value["affiliate_conversions"] = 0
            with self.subTest(report_status=report_status):
                self.assertEqual(subject.build_review(value).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
