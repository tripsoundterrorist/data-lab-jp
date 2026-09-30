import json
import subprocess
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
    def test_current_state_is_preview_only_until_human_approval(self):
        result = build()
        self.assertEqual(result.status, gate.PREVIEW_ONLY)
        self.assertFalse(result.manual_post_candidate)
        self.assertNotIn("SNS_CONDITIONS_NOT_VERIFIED", result.reason_codes)
        self.assertNotIn("SNS_OFFICIAL_ANSWERS_PENDING", result.reason_codes)

    def test_current_answers_and_human_approval_create_manual_candidate(self):
        result = build(explicit_human_approval=True)
        self.assertEqual(result.status, gate.READY_FOR_MANUAL_POST)
        self.assertTrue(result.manual_post_candidate)

    def test_unverified_site_funnel_stays_blocked(self):
        entries = dict(matrix.current_entries())
        entries["SNS_TO_SITE_TO_FANZA_FUNNEL"] = matrix.AnswerDecision(
            matrix.CONDITIONALLY_ALLOWED
        )
        result = build(
            official_answer_entries=entries, explicit_human_approval=True
        )
        self.assertEqual(result.status, gate.PREVIEW_ONLY)
        self.assertIn("SNS_CONDITIONS_NOT_VERIFIED", result.reason_codes)

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
        self.assertTrue(text.startswith("【PR】"))
        self.assertIn("独自集計", text)
        self.assertIn("非公式", text)

    def test_preview_and_approved_reason_codes_are_distinct(self):
        self.assertEqual(
            build().reason_codes, ("EXPLICIT_HUMAN_APPROVAL_REQUIRED",)
        )
        self.assertEqual(
            build(explicit_human_approval=True).reason_codes,
            ("MANUAL_POST_CANDIDATE_READY",),
        )

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

    def test_item_landing_can_preselect_safe_price_discovery(self):
        result = build(
            landing_path="/items/", public_data_available=True,
            landing_sort="price-asc", landing_price_band="under-1000",
        )
        self.assertEqual(result.status, gate.PREVIEW_ONLY)
        self.assertIn("sort=price-asc", result.candidate_text)
        self.assertIn("price_band=under-1000", result.candidate_text)

    def test_item_landing_state_is_allowlisted_and_item_only(self):
        self.assertEqual(
            build(landing_sort="price-asc").status, gate.BLOCKED
        )
        self.assertEqual(
            build(
                landing_path="/items/", public_data_available=True,
                landing_sort="rank",
            ).status,
            gate.BLOCKED,
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

    def test_output_is_within_x_weighted_character_limit(self):
        result = build()
        self.assertLessEqual(result.weighted_length, gate.X_MAX_WEIGHTED_LENGTH)
        self.assertEqual(result.weighted_length, gate.x_weighted_length(result.candidate_text))

    def test_long_tracking_url_counts_as_t_co_length(self):
        result = build(
            landing_path="/items/", public_data_available=True,
            landing_sort="price-asc", landing_price_band="under-1000",
            campaign="price_under_1000_20260930",
        )
        self.assertEqual(result.status, gate.PREVIEW_ONLY)
        self.assertGreater(len(result.candidate_text), result.weighted_length)
        self.assertEqual(result.candidate_text.count("https://"), 1)

    def test_excessive_weighted_copy_fails_closed(self):
        result = build(fact_text="確" * 140)
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertIsNone(result.candidate_text)
        self.assertGreater(result.weighted_length, gate.X_MAX_WEIGHTED_LENGTH)
        self.assertIn("POST_LENGTH_EXCEEDED", result.reason_codes)

    def test_weighted_counter_uses_23_for_each_url(self):
        self.assertEqual(gate.x_weighted_length("A https://example.com/very/long/path B"), 27)

    def test_cli_preview_targets_live_product_catalog(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "revenue_mvp_x_funnel_candidate.py")],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], gate.PREVIEW_ONLY)
        self.assertIn("https://datalabx.jp/items/?", output["candidate_text"])
        self.assertIn("utm_campaign=product_catalog", output["candidate_text"])
        self.assertIn("FANZA動画100作品", output["candidate_text"])
        self.assertFalse(output["posting_performed"])
