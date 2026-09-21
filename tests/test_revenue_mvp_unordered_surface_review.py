from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_lifecycle_policy as lifecycle  # noqa: E402
import revenue_mvp_unordered_surface_review as review  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402


NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)


def candidate() -> lifecycle.OfficialLifecycleDecision:
    return lifecycle.evaluate_official_lifecycle_policy(
        VerificationObservation(
            observation=Observation.API_ITEM_VISIBLE,
            observed_at=NOW,
            expected_content_id_match=True,
            affiliate_link_observed=True,
            source_status_code=200,
            reason_codes=("SANITIZED_FIXTURE",),
        )
    )


def evaluate(**overrides):
    values = {
        "contract_version": review.CONTRACT_VERSION,
        "lifecycle_freshness_confirmed": True,
        "api_observed_at": NOW,
        "public_fields": {
            "title", "current_price", "price_observed_at", "api_observed_at",
            "transparency_notice",
        },
        "public_claim_codes": {
            "API_OBSERVED_AT", "PRICE_OBSERVED_AT", "UNORDERED_PRESENTATION",
        },
        "presentation_mode": review.PRESENTATION_MODE,
        "sort_controls_present": False,
        "position_indicators_present": False,
        "history_present": False,
        "affiliate_cta_requested": False,
        "title_snapshot_provenance_confirmed": True,
        "transparency_notice": review.TRANSPARENCY_NOTICE,
        "price_observed_at": NOW,
    }
    values.update(overrides)
    return review.review_unordered_surface(candidate(), **values)


class UnorderedSurfaceReviewTests(unittest.TestCase):
    def assert_non_activation(self, result):
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.affiliate_eligibility_allowed)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.cta_allowed)
        self.assertFalse(result.api_order_label_allowed)

    def test_valid_unordered_price_surface_is_manual_review_candidate_only(self):
        result = evaluate()
        self.assertEqual(result.status, review.REVIEW_CANDIDATE)
        self.assertTrue(result.eligible_for_manual_gate_review)
        self.assertTrue(result.price_display_allowed)
        self.assertEqual(result.timestamp_label, "API取得確認時刻")
        self.assert_non_activation(result)

    def test_price_is_optional_but_cannot_be_partially_or_stalely_described(self):
        without_price = evaluate(
            public_fields={"title", "api_observed_at", "transparency_notice"},
            public_claim_codes={"API_OBSERVED_AT", "UNORDERED_PRESENTATION"},
            price_observed_at=None,
        )
        self.assertEqual(without_price.status, review.REVIEW_CANDIDATE)
        self.assertFalse(without_price.price_display_allowed)
        for values in (
            {"public_fields": {"title", "current_price", "api_observed_at", "transparency_notice"}},
            {"price_observed_at": NOW - timedelta(seconds=1)},
        ):
            with self.subTest(values=values):
                self.assertEqual(evaluate(**values).status, review.BLOCKED)

    def test_order_position_history_and_cta_are_fail_closed(self):
        for key in (
            "sort_controls_present", "position_indicators_present", "history_present",
            "affiliate_cta_requested",
        ):
            with self.subTest(key=key):
                self.assertEqual(evaluate(**{key: True}).status, review.BLOCKED)

    def test_forbidden_fields_and_claims_are_fail_closed(self):
        for field in review.FORBIDDEN_PUBLIC_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    evaluate(public_fields={
                        "title", "api_observed_at", "transparency_notice", field
                    }).status,
                    review.BLOCKED,
                )
        for claim in review.FORBIDDEN_CLAIM_CODES:
            with self.subTest(claim=claim):
                self.assertEqual(
                    evaluate(public_claim_codes={
                        "API_OBSERVED_AT", "UNORDERED_PRESENTATION", claim
                    }).status,
                    review.BLOCKED,
                )

    def test_missing_or_mismatched_provenance_blocks_review(self):
        cases = (
            {"lifecycle_freshness_confirmed": False},
            {"api_observed_at": NOW + timedelta(seconds=1)},
            {"title_snapshot_provenance_confirmed": False},
            {"transparency_notice": "別の注意書き"},
            {"contract_version": "0.2"},
        )
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(evaluate(**values).status, review.REVIEW_CANDIDATE)

    def test_non_candidate_lifecycle_cannot_enter_manual_review(self):
        decision = replace(candidate(), state=lifecycle.EligibilityState.EXCLUDED)
        result = review.review_unordered_surface(
            decision,
            contract_version=review.CONTRACT_VERSION,
            lifecycle_freshness_confirmed=True,
            api_observed_at=NOW,
            public_fields={"title", "api_observed_at", "transparency_notice"},
            public_claim_codes={"API_OBSERVED_AT", "UNORDERED_PRESENTATION"},
            presentation_mode=review.PRESENTATION_MODE,
            sort_controls_present=False,
            position_indicators_present=False,
            history_present=False,
            affiliate_cta_requested=False,
            title_snapshot_provenance_confirmed=True,
            transparency_notice=review.TRANSPARENCY_NOTICE,
        )
        self.assertEqual(result.status, review.BLOCKED)
        self.assert_non_activation(result)

    def test_module_accepts_no_source_order_urls_ids_or_io(self):
        source = Path(review.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "source_sort:", "affiliate_url:", "content_id:", "sqlite3", "requests",
            "urllib", "open(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
