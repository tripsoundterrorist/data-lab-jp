"""Synthetic inputs only: no browser, network, GA4 or production access."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from scripts.article_navigation_review import build_review, ROUTES

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def fixture():
    return {"version": "0.1", "source": "GA4_PROCESSED_REPORT",
            "period_start": "2026-10-19", "period_end": "2026-10-21",
            "observed_at": "2026-10-22T12:00:00+09:00",
            "acquired": True, "processing_complete": True,
            "rows": [{"navigation_route": route, "event_count": 3,
                      "test_status": "VERIFIED", "test_count": 1} for route in ROUTES]}


class ArticleNavigationReviewTests(unittest.TestCase):
    def review(self, value):
        return build_review(value, now=NOW)

    def test_verified_counts_and_input_unchanged(self):
        value = fixture()
        before = deepcopy(value)
        result = self.review(value)
        self.assertEqual(result["status"], "READY_FOR_MANUAL_REVIEW")
        self.assertEqual(result["total_events"], 9)
        self.assertEqual(result["non_test_events"], 6)
        self.assertEqual(result["rates"], "NOT_ACQUIRED")
        self.assertEqual(result["attribution"], "NOT_ESTABLISHED")
        self.assertFalse(result["external_write_performed"])
        self.assertFalse(result["production_write_performed"])
        self.assertEqual(value, before)

    def test_unknown_test_effect_never_subtracted_or_called_non_test_outcome(self):
        value = fixture()
        value["rows"][0].update(test_status="UNCONFIRMED", test_count=None)
        result = self.review(value)
        self.assertEqual(result["total_events"], 9)
        self.assertIsNone(result["non_test_events"])
        self.assertIsNone(result["routes"][0]["non_test_events"])
        self.assertEqual(result["status"], "ADDITIONAL_CONFIRMATION_REQUIRED")

    def test_missing_and_processing_delay_are_not_zero(self):
        for acquired, processed in ((False, False), (False, True), (True, False)):
            value = fixture()
            value.update(acquired=acquired, processing_complete=processed, rows=[])
            result = self.review(value)
            self.assertEqual(result["status"], "NOT_ACQUIRED")
            self.assertIsNone(result["total_events"])

    def test_explicit_verified_zeros_only(self):
        value = fixture()
        for row in value["rows"]:
            row.update(event_count=0, test_count=0)
        result = self.review(value)
        self.assertEqual(result["non_test_events"], 0)
        value["rows"] = []
        self.assertEqual(self.review(value)["status"], "BLOCKED")

    def test_invalid_rows_fail_closed(self):
        cases = []
        for key, invalid in (("navigation_route", "unknown"), ("navigation_route", []),
                             ("event_count", True), ("event_count", -1),
                             ("test_count", True), ("test_count", 4),
                             ("test_count", -1), ("test_status", "guessed")):
            value = fixture()
            value["rows"][0][key] = invalid
            cases.append(value)
        value = fixture(); value["rows"][0]["private_data"] = "fixture"; cases.append(value)
        value = fixture(); value["rows"][1] = deepcopy(value["rows"][0]); cases.append(value)
        value = fixture(); value["processing_complete"] = False; cases.append(value)
        for value in cases:
            with self.subTest(value=value):
                result = self.review(value)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIsNone(result["total_events"])
                self.assertEqual(result["routes"], [])

    def test_extreme_timezone_conversion_fails_closed(self):
        value = fixture()
        value["observed_at"] = "9999-12-31T23:00:00+00:00"
        result = build_review(value, now=datetime.max.replace(tzinfo=timezone.utc))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["total_events"])

    def test_period_source_schema_and_clock_boundaries(self):
        for key, invalid in (("period_start", "2026-10-18"),
                             ("period_end", "2026-11-22"),
                             ("period_end", "2026-10-18"),
                             ("observed_at", "2026-10-21T23:00:00+09:00"),
                             ("observed_at", "2026-10-24T12:00:00+09:00"),
                             ("observed_at", "2026-10-22T12:00:00"),
                             ("observed_at", None), ("source", "REALTIME"),
                             ("acquired", 1), ("version", "unknown")):
            value = fixture(); value[key] = invalid
            with self.subTest(key=key, invalid=invalid):
                self.assertEqual(self.review(value)["status"], "BLOCKED")
        value = fixture(); value["unknown"] = True
        self.assertEqual(self.review(value)["status"], "BLOCKED")
        self.assertEqual(self.review(None)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
