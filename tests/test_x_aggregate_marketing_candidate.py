from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import x_aggregate_marketing_candidate as subject  # noqa: E402


def build(**changes):
    values = {
        "fact_text": (
            "公開中の100作品を価格帯で集計。1,000円未満33作品、"
            "1,000〜1,999円45作品、2,000〜2,999円22作品。中央値は1,730円。"
        ),
        "theme": "price_distribution",
        "source_type": "public_site_snapshot",
        "source_ids": ["public:datalabx.jp/items/20260930t070013z"],
        "source_checked_at": "2026-09-30T16:00:13+09:00",
        "aggregate_facts": {
            "item_count": 100,
            "under_1000": 33,
            "from_1000_to_1999": 45,
            "from_2000_to_2999": 22,
            "median_yen": 1730,
        },
    }
    values.update(changes)
    return subject.build_candidate(**values)


class AggregateMarketingCandidateTests(unittest.TestCase):
    def test_safe_aggregate_stops_at_compliance_review(self):
        result = build()
        self.assertEqual(result.status, subject.READY_FOR_COMPLIANCE_REVIEW)
        self.assertEqual(result.reason_codes, ("COMPLIANCE_REVIEW_REQUIRED",))
        self.assertFalse(result.manual_post_candidate)
        self.assertFalse(result.posting_performed)
        self.assertFalse(result.automatic_post_allowed)
        self.assertFalse(result.affiliate_promotion_allowed)
        self.assertFalse(result.product_media_allowed)

    def test_urls_promotional_language_and_pr_are_blocked(self):
        for value in (
            "https://datalabx.jp を確認",
            "【PR】公開中の作品です",
            "今すぐ購入",
            "おすすめ作品を集計",
            "人気No.1です",
        ):
            with self.subTest(value=value):
                self.assertEqual(build(fact_text=value).status, subject.BLOCKED)

    def test_sources_timestamp_and_aggregate_are_required(self):
        cases = (
            {"source_ids": []},
            {"source_ids": ["secret value"]},
            {"source_checked_at": "2026-09-30"},
            {"source_type": "private_api_dump"},
            {"aggregate_facts": {}},
            {"aggregate_facts": {"item_count": -1}},
            {"aggregate_facts": {"title": "product name"}},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(build(**changes).status, subject.BLOCKED)

    def test_only_explicit_aggregate_themes_are_allowed(self):
        self.assertEqual(build(theme="affiliate_offer").status, subject.BLOCKED)
        for theme in subject.THEMES:
            with self.subTest(theme=theme):
                self.assertEqual(
                    build(theme=theme).status,
                    subject.READY_FOR_COMPLIANCE_REVIEW,
                )

    def test_recorded_candidate_matches_the_gate(self):
        path = ROOT / "docs" / "evidence" / "x-aggregate-price-candidate-20261004.json"
        recorded = json.loads(path.read_text(encoding="utf-8"))
        result = subject.build_candidate(
            fact_text=recorded["candidate_text"],
            theme=recorded["theme"],
            source_type=recorded["source_type"],
            source_ids=recorded["source_ids"],
            source_checked_at=recorded["source_checked_at"],
            aggregate_facts=recorded["aggregate_facts"],
        )
        self.assertEqual(result.status, recorded["status"])
        self.assertFalse(result.manual_post_candidate)


if __name__ == "__main__":
    unittest.main()
