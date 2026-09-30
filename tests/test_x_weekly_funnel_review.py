from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import x_weekly_funnel_review as subject  # noqa: E402


def row():
    return {
        "post_url_or_id": "https://x.com/datalab_jp/status/1",
        "posted_at_jst": "2026-09-28T09:30:00+09:00",
        "theme": "price_change", "pr_link": True,
        "campaign": "price_under_1000_20260928",
        "impressions": 100, "non_follower_reach": subject.NOT_ACQUIRED,
        "engagements": 8, "profile_visits": 3, "follows": 1,
        "link_clicks": 5, "ga_sessions": 4, "outbound_product_clicks": 2,
    }


def payload():
    return {
        "version": "0.1", "period_start": "2026-09-28",
        "period_end": "2026-10-04", "posts": [row()],
    }


class WeeklyFunnelReviewTests(unittest.TestCase):
    def test_missing_values_are_preserved_without_partial_total(self):
        result = subject.build_review(payload())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.metric_summaries["impressions"]["total"], 100)
        self.assertEqual(
            result.metric_summaries["non_follower_reach"]["total"],
            subject.NOT_ACQUIRED,
        )
        self.assertEqual(result.post_rates[0]["x_link_ctr"], 0.05)
        self.assertEqual(result.post_rates[0]["site_cta_rate"], 0.5)
        self.assertEqual(result.disposition, "ADDITIONAL_CONFIRMATION_REQUIRED")
        self.assertFalse(result.external_write_performed)

    def test_zero_or_missing_denominator_does_not_invent_rate(self):
        value = payload()
        value["posts"][0]["impressions"] = 0
        value["posts"][0]["link_clicks"] = 0
        value["posts"][0]["ga_sessions"] = subject.NOT_ACQUIRED
        result = subject.build_review(value)
        self.assertEqual(result.post_rates[0]["x_link_ctr"], subject.NOT_ACQUIRED)
        self.assertEqual(result.post_rates[0]["site_cta_rate"], subject.NOT_ACQUIRED)

    def test_duplicate_unknown_invalid_and_out_of_period_fail_closed(self):
        cases = []
        duplicate = payload(); duplicate["posts"].append(deepcopy(duplicate["posts"][0])); cases.append(duplicate)
        unknown = payload(); unknown["posts"][0]["extra"] = 1; cases.append(unknown)
        invalid = payload(); invalid["posts"][0]["impressions"] = -1; cases.append(invalid)
        outside = payload(); outside["posts"][0]["posted_at_jst"] = "2026-10-05T09:30:00+09:00"; cases.append(outside)
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(subject.build_review(value).status, subject.BLOCKED)

    def test_period_timezone_theme_campaign_and_boolean_are_strict(self):
        changes = (
            ("period_start", "2026-09-29"),
            ("posted_at_jst", "2026-09-28T09:30:00Z"),
            ("theme", "viral"), ("campaign", "unsafe value"), ("pr_link", 1),
        )
        for field, invalid in changes:
            value = payload()
            if field in {"period_start", "period_end"}:
                value[field] = invalid
            else:
                value["posts"][0][field] = invalid
            with self.subTest(field=field):
                self.assertEqual(subject.build_review(value).status, subject.BLOCKED)

    def test_clicks_cannot_exceed_impressions(self):
        value = payload(); value["posts"][0]["link_clicks"] = 101
        result = subject.build_review(value)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("CLICK_COUNT_EXCEEDS_IMPRESSIONS", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
