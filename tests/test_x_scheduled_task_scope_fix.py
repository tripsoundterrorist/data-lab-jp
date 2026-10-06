import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSIS = (
    ROOT / "docs" / "evidence" / "x-scheduled-task-overblocking-diagnosis-20261006.json"
)
FIX = ROOT / "docs" / "operations" / "chatgpt-x-scheduled-task-scope-fix-v0.2.md"
POLICY = ROOT / "docs" / "policies" / "x-aggregate-marketing-compliance-review-v0.1.md"


class XScheduledTaskScopeFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(DIAGNOSIS.read_text(encoding="utf-8"))
        cls.fix = FIX.read_text(encoding="utf-8")
        cls.policy = POLICY.read_text(encoding="utf-8")

    def test_diagnosis_binds_block_to_exact_reviewed_packet(self):
        packet = self.value["blocked_packet"]
        self.assertEqual(packet["batch_id"], "x-aggregate-20261004-a")
        self.assertEqual(
            packet["packet_sha256"],
            "82c31e97dda1715317e52402030192fd7ab19fbe124043869dd915f2b0dc7a28",
        )
        self.assertEqual(packet["candidate_count"], 3)
        self.assertTrue(self.value["diagnosis"]["packet_specific_decision_applied_globally"])
        self.assertFalse(self.value["diagnosis"]["global_x_posting_prohibition_established"])

    def test_risky_content_remains_blocked(self):
        forbidden = set(self.value["generic_fallback_forbidden_elements"])
        self.assertEqual(len(forbidden), 9)
        for required in (
            "DMM_OR_FANZA_REFERENCE",
            "SITE_URL_OR_DOMAIN",
            "AFFILIATE_OR_PR_WORDING",
            "PRODUCT_PRICE_RANKING_OR_REVIEW_FACT",
            "PRODUCT_IMAGE_OR_BRAND_CHART",
        ):
            self.assertIn(required, forbidden)

    def test_fix_keeps_fallback_preview_only_and_manual(self):
        for value in (
            "PREVIEW_ONLY",
            "日本語140字以内",
            "Xへの投稿・予約・プロフィール変更を行わない",
            "過去候補と同一または近似する本文は生成しない",
            "新しい定時タスクを作らず",
        ):
            self.assertIn(value, self.fix)
        self.assertFalse(self.value["posting_allowed"])
        self.assertFalse(self.value["automatic_posting_allowed"])
        self.assertFalse(self.value["schedule_change_performed"])

    def test_policy_explicitly_rejects_global_application(self):
        self.assertIn("hash-bound to batch `x-aggregate-20261004-a`", self.policy)
        self.assertIn("not evidence of an X-wide ban", self.policy)
        self.assertIn("`PREVIEW_ONLY` generic data-literacy draft", self.policy)


if __name__ == "__main__":
    unittest.main()
