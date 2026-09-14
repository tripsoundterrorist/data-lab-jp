from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "policies" / "sns-x-operations-v0.1.md"


class SnsXOperationsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = POLICY.read_text(encoding="utf-8")

    def test_current_state_stays_preview_only(self):
        self.assertIn("SNS_ACCOUNT_REGISTRATION` is verified", self.content)
        for topic in (
            "SNS_TO_SITE_TO_FANZA_FUNNEL",
            "SNS_PRODUCT_MEDIA_USE",
            "AUTOMATED_FACT_POSTING",
        ):
            self.assertIn(topic, self.content)
        self.assertIn("X remains `PREVIEW_ONLY`", self.content)
        self.assertIn("performs no X post", self.content)

    def test_external_schedule_is_documented_without_registration(self):
        for value in ("2026-09-15", "2026-10-25", "09:30", "12:30", "19:30"):
            self.assertIn(value, self.content)
        self.assertIn("Do not duplicate it", self.content)
        self.assertIn("daily 19:00", self.content)
        self.assertIn("daily 07:00", self.content)

    def test_draft_and_measurement_controls_are_explicit(self):
        for value in (
            "140 Japanese",
            "`【PR】`",
            "Price change: 30%",
            "Ranking change: 25%",
            "link clicks",
            "CTR",
            "time alone",
        ):
            self.assertIn(value, self.content)

    def test_weekly_review_uses_observed_inputs_and_explicit_dispositions(self):
        for value in (
            "once each week",
            "Monday-through-Sunday",
            "NOT_ACQUIRED",
            "post_url_or_id",
            "non_follower_reach",
            "possible confounders",
            "MAINTAIN",
            "SMALL_CHANGE_PROPOSAL",
            "STOP_RECOMMENDED",
            "ADDITIONAL_CONFIRMATION_REQUIRED",
        ):
            self.assertIn(value, self.content)

    def test_research_and_change_boundaries_preserve_current_test(self):
        for value in (
            "official X Help Center",
            "adult content",
            "spam/platform",
            "API fees",
            "through 2026-10-25",
            "Major time-slot changes wait",
            "modify X, ChatGPT schedules, GitHub configuration",
            "explicit user approval",
            "Do not create a draft-generation automation",
        ):
            self.assertIn(value, self.content)

    def test_automation_remains_staged_and_fail_closed(self):
        for value in (
            "independently stoppable stages",
            "fail closed",
            "human approval before posting",
            "idempotency",
            "emergency stop",
            "auto-unlock",
            "Result retrieval",
            "separately stoppable, idempotent, auditable",
        ):
            self.assertIn(value, self.content)


if __name__ == "__main__":
    unittest.main()
