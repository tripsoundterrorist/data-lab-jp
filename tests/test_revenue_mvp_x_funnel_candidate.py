import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_answer_matrix as matrix  # noqa: E402
import revenue_mvp_x_funnel_candidate as gate  # noqa: E402


def answers():
    return {topic: matrix.AnswerDecision(matrix.ALLOWED) for topic in matrix.TOPIC_IDS}


def build(**changes):
    values = {
        "fact_text": "価格データの観測状況を更新しました。",
        "landing_path": "/column-price", "campaign": "price_update",
    }
    values.update(changes)
    return gate.build_candidate(**values)


class XFunnelCandidateTests(unittest.TestCase):
    def test_current_state_is_preview_only(self):
        result = build()
        self.assertEqual(result.status, gate.PREVIEW_ONLY)
        self.assertFalse(result.manual_post_candidate)
        self.assertIn("SNS_OFFICIAL_ANSWERS_PENDING", result.reason_codes)

    def test_complete_answers_still_require_human_approval(self):
        result = build(official_answer_entries=answers())
        self.assertEqual(result.status, gate.PREVIEW_ONLY)
        self.assertFalse(result.manual_post_candidate)

    def test_complete_answers_and_approval_create_manual_candidate(self):
        result = build(official_answer_entries=answers(), explicit_human_approval=True)
        self.assertEqual(result.status, gate.READY_FOR_MANUAL_POST)
        self.assertTrue(result.manual_post_candidate)
        self.assertFalse(result.posting_performed)
        self.assertFalse(result.automatic_post_allowed)

    def test_candidate_targets_only_datalabx_with_fixed_utm(self):
        text = build().candidate_text
        self.assertIn("https://datalabx.jp/column-price?", text)
        self.assertIn("utm_source=x", text)
        self.assertNotIn("fanza", text.casefold())

    def test_disclosure_is_always_appended(self):
        text = build().candidate_text
        self.assertIn("独自集計", text)
        self.assertIn("非公式", text)

    def test_direct_urls_mentions_hashtags_and_urgency_are_blocked(self):
        for value in ("https://example.invalid", "@user", "#tag", "今だけ", "公式ランキング"):
            with self.subTest(value=value):
                self.assertEqual(build(fact_text=value).status, gate.BLOCKED)

    def test_item_path_requires_public_data(self):
        self.assertEqual(build(landing_path="/items/").status, gate.BLOCKED)
        self.assertEqual(
            build(landing_path="/items/", public_data_available=True).status,
            gate.PREVIEW_ONLY,
        )

    def test_unknown_path_and_campaign_are_blocked(self):
        self.assertEqual(build(landing_path="/items/item").status, gate.BLOCKED)
        self.assertEqual(build(campaign="bad value").status, gate.BLOCKED)

    def test_no_media_or_direct_affiliate_permission(self):
        result = build()
        self.assertFalse(result.media_allowed)
        self.assertFalse(result.direct_affiliate_link_allowed)

    def test_safe_result_has_no_credentials(self):
        output = json.dumps(build().to_dict(), ensure_ascii=False)
        self.assertNotIn("affiliate_id", output)
        self.assertNotIn("credential", output)

    def test_non_boolean_flags_fail_closed(self):
        self.assertEqual(build(public_data_available=1).status, gate.BLOCKED)
        self.assertEqual(build(explicit_human_approval=1).status, gate.BLOCKED)

    def test_output_is_within_x_character_limit(self):
        self.assertLessEqual(len(build().candidate_text), 280)
