from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "policies" / "sns-x-operations-v0.1.md"
PREMIUM_TASK = ROOT / "docs" / "operations" / "chatgpt-x-scheduled-task-premium-prompt-v0.1.md"


class SnsXOperationsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = POLICY.read_text(encoding="utf-8")
        cls.premium_task = PREMIUM_TASK.read_text(encoding="utf-8")

    def test_current_state_stays_preview_only(self):
        self.assertIn("SNS_ACCOUNT_REGISTRATION` is verified", self.content)
        for topic in (
            "SNS_TO_SITE_TO_FANZA_FUNNEL",
            "SNS_PRODUCT_MEDIA_USE",
            "AUTOMATED_FACT_POSTING",
        ):
            self.assertIn(topic, self.content)
        self.assertIn("remain preview-only until explicit human approval", self.content)
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

    def test_premium_is_a_bounded_experiment_not_a_compliance_override(self):
        for value in (
            "`@datalab_jp` to Premium on 2026-10-01",
            "bounded 30-day acquisition",
            "X_ADULT_AFFILIATE_PAID_PARTNERSHIP_BLOCKED",
            "link-free, non-promotional",
            "pre-upgrade baseline",
            "confirmed revenue",
            "missing metrics cannot support renewal",
            "Do not upgrade to Premium+",
        ):
            self.assertIn(value, self.content)

    def test_chatgpt_task_prompt_uses_premium_without_duplicating_schedule(self):
        for value in (
            "Monday/Thursday 09:30",
            "Tuesday/Friday 12:30",
            "Wednesday/Sunday 19:30",
            "Saturday task",
            "does not create another schedule",
            "X_ADULT_AFFILIATE_PAID_PARTNERSHIP_BLOCKED",
            "通常は日本語140字以内",
            "日曜日だけ",
            "300〜600字",
            "画像候補を付けるのは毎週月曜日だけ",
            "投稿操作は必ずユーザーが手動",
        ):
            self.assertIn(value, self.premium_task)

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

    def test_deep_research_is_exceptional_and_proposal_only(self):
        for value in (
            "lightweight check",
            "Deep Research is optional only",
            "sources conflict",
            "Do not use it by default",
            "report why escalation was",
            "research scope",
            "primary-source findings from",
            "evidence for a proposal, not approval",
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
