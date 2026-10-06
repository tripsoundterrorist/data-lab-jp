import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "chatgpt-x-scheduled-task-scope-fix-applied-20261006.json"
)


class ChatGptXScheduledTaskScopeFixAppliedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_weekly_schedule_is_preserved(self):
        tasks = self.value["active_draft_tasks"]
        self.assertEqual(len(tasks), 3)
        self.assertEqual(
            [(row["name"], row["days"], row["time"]) for row in tasks],
            [
                ("Xテスト 9:30", ["MONDAY", "THURSDAY"], "09:30"),
                ("Xテスト 12:30", ["TUESDAY", "FRIDAY"], "12:30"),
                ("Xテスト 19:30", ["WEDNESDAY", "SUNDAY"], "19:30"),
            ],
        )
        for row in tasks:
            self.assertEqual(row["timezone"], "Asia/Tokyo")
            self.assertEqual(row["end_date"], "2026-10-25")
            self.assertTrue(row["scope_fix_present"])

    def test_duplicate_is_paused_not_deleted(self):
        self.assertEqual(len(self.value["paused_duplicate_tasks"]), 1)
        duplicate = self.value["paused_duplicate_tasks"][0]
        self.assertEqual(duplicate["name"], "Xテスト P2 9:30")
        self.assertTrue(duplicate["paused"])
        self.assertFalse(duplicate["deleted"])

    def test_preview_and_manual_boundaries_remain(self):
        behavior = self.value["scope_fix_behavior"]
        self.assertEqual(behavior["generic_data_literacy_fallback"], "PREVIEW_ONLY")
        self.assertTrue(behavior["link_or_affiliate_promotion_blocked"])
        self.assertTrue(behavior["adult_or_product_specific_content_blocked"])
        self.assertTrue(behavior["manual_posting_only"])
        self.assertFalse(self.value["task_run_performed_for_verification"])
        self.assertFalse(self.value["x_post_performed"])
        self.assertFalse(self.value["x_schedule_or_profile_change_performed"])
        self.assertFalse(self.value["new_task_created"])

    def test_no_private_identifiers_or_secrets_are_stored(self):
        self.assertFalse(self.value["secret_or_private_identifier_stored"])
        rendered = json.dumps(self.value, ensure_ascii=False).casefold()
        for forbidden in (
            "automationid",
            "messageid",
            "http://",
            "https://",
            "password",
            "cookie",
            "api_id",
            "affiliate_id",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
