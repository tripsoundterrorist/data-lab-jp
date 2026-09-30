import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_x_link_free_candidate as subject  # noqa: E402


def build(**changes):
    values = {
        "fact_text": "取得できない値は推測せず、未取得として扱います。",
        "theme": "transparency",
        "source_ids": ["github:docs/policies/sns-x-operations-v0.1.md"],
        "source_checked_at": "2026-10-01T09:00:00+09:00",
    }
    values.update(changes)
    return subject.build_candidate(**values)


class LinkFreeXCandidateTests(unittest.TestCase):
    def test_verified_copy_stays_preview_until_human_approval(self):
        result = build()
        self.assertEqual(result.status, subject.PREVIEW_ONLY)
        self.assertFalse(result.manual_post_candidate)
        self.assertEqual(result.reason_codes, ("EXPLICIT_HUMAN_APPROVAL_REQUIRED",))

    def test_human_approval_makes_only_manual_link_free_candidate(self):
        result = build(explicit_human_approval=True)
        self.assertEqual(result.status, subject.READY_FOR_MANUAL_POST)
        self.assertTrue(result.manual_post_candidate)
        self.assertFalse(result.posting_performed)
        self.assertFalse(result.automatic_post_allowed)
        self.assertFalse(result.link_included)
        self.assertFalse(result.affiliate_promotion_allowed)

    def test_urls_pr_affiliate_and_commercial_ctas_are_blocked(self):
        for value in (
            "https://datalabx.jp",
            "【PR】集計方法です",
            "今すぐ購入",
            "おすすめ作品",
            "アフィリエイト情報",
        ):
            with self.subTest(value=value):
                self.assertEqual(build(fact_text=value).status, subject.BLOCKED)

    def test_only_non_promotional_themes_are_allowed(self):
        self.assertEqual(build(theme="price_change").status, subject.BLOCKED)
        for theme in subject.THEMES:
            with self.subTest(theme=theme):
                self.assertEqual(build(theme=theme).status, subject.PREVIEW_ONLY)

    def test_source_and_timestamp_are_required_and_bounded(self):
        cases = (
            {"source_ids": []},
            {"source_ids": ["secret value"]},
            {"source_ids": ["github:a", "github:a"]},
            {"source_checked_at": "2026-10-01"},
            {"source_checked_at": None},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(build(**changes).status, subject.BLOCKED)

    def test_non_boolean_approval_fails_closed(self):
        self.assertEqual(build(explicit_human_approval=1).status, subject.BLOCKED)

    def test_cli_outputs_safe_preview_without_link_or_pr(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "revenue_mvp_x_link_free_candidate.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], subject.PREVIEW_ONLY)
        self.assertFalse(output["link_included"])
        self.assertNotIn("http", output["candidate_text"])
        self.assertNotIn("【PR】", output["candidate_text"])


if __name__ == "__main__":
    unittest.main()
