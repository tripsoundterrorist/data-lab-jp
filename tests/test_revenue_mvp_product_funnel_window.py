from datetime import date
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_funnel_window as subject  # noqa: E402


def evidence():
    return json.loads(subject.DIMENSIONS_EVIDENCE.read_text(encoding="utf-8"))


class ProductFunnelWindowTests(unittest.TestCase):
    def test_october_first_waits_for_complete_window_and_processing(self):
        result = subject.assess(evidence(), date(2026, 10, 1))
        self.assertEqual(result.status, subject.WAITING)
        self.assertEqual(result.period_start, "2026-10-02")
        self.assertEqual(result.period_end, "2026-10-08")
        self.assertEqual(result.earliest_manual_review_date, "2026-10-10")
        self.assertFalse(result.product_funnel_window_closed)
        self.assertFalse(result.ga4_export_allowed)
        self.assertFalse(result.expansion_decision_allowed)
        self.assertFalse(result.production_change_allowed)

    def test_review_date_allows_only_manual_export(self):
        result = subject.assess(evidence(), date(2026, 10, 10))
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.product_funnel_window_closed)
        self.assertTrue(result.ga4_export_allowed)
        self.assertFalse(result.expansion_decision_allowed)
        self.assertFalse(result.production_change_allowed)
        self.assertIn("MANUAL_GA4_EXPORT_REQUIRED", result.reason_codes)

    def test_nonretroactive_or_dimension_change_blocks(self):
        for change in (
            ("retroactive", True),
            ("expected_reporting_delay", "UNKNOWN"),
            ("custom_dimensions", []),
        ):
            value = evidence()
            value[change[0]] = change[1]
            with self.subTest(change=change):
                self.assertEqual(
                    subject.assess(value, date(2026, 10, 10)).status,
                    subject.BLOCKED,
                )

    def test_unknown_schema_fails_closed(self):
        value = evidence()
        value["extra"] = True
        result = subject.assess(value, date(2026, 10, 10))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.ga4_export_allowed)


if __name__ == "__main__":
    unittest.main()
