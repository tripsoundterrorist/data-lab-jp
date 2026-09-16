from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_lifecycle_policy as policy  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402


NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)


def observed(value: Observation, affiliate: bool | None) -> VerificationObservation:
    expected_match = (
        True if value is Observation.API_ITEM_VISIBLE
        else False if value is Observation.API_ITEM_NOT_RETURNED
        else None
    )
    return VerificationObservation(
        observation=value,
        observed_at=NOW,
        expected_content_id_match=expected_match,
        affiliate_link_observed=affiliate,
        source_status_code=200,
        reason_codes=("SANITIZED_FIXTURE",),
    )


class OfficialLifecyclePolicyTests(unittest.TestCase):
    def assert_gates_closed(self, result: policy.OfficialLifecycleDecision) -> None:
        self.assertFalse(result.publication_gate_change_allowed)
        self.assertFalse(result.internal_history_retention_allowed)
        self.assertFalse(result.public_rank_number_allowed)
        self.assertFalse(result.offset_rank_allowed)
        self.assertFalse(result.update_frequency_claim_allowed)

    def test_api_item_not_returned_is_excluded_and_requery_has_no_frequency(self):
        result = policy.evaluate_official_lifecycle_policy(
            observed(Observation.API_ITEM_NOT_RETURNED, None)
        )
        self.assertEqual(result.state, policy.EligibilityState.EXCLUDED)
        self.assertTrue(result.exclude_from_public_site)
        self.assertFalse(result.affiliate_candidate)
        self.assertTrue(result.requery_permitted)
        self.assertEqual(result.wait_seconds_upper_bound, 0)
        self.assert_gates_closed(result)

    def test_absent_or_unknown_affiliate_url_is_excluded(self):
        for value in (False, None):
            with self.subTest(value=value):
                result = policy.evaluate_official_lifecycle_policy(
                    observed(Observation.API_ITEM_VISIBLE, value)
                )
                self.assertEqual(result.state, policy.EligibilityState.EXCLUDED)
                self.assertTrue(result.exclude_from_public_site)
                self.assertFalse(result.public_listing_candidate)
                self.assert_gates_closed(result)

    def test_errors_require_one_bounded_retry_and_rate_limit_stop(self):
        for value in (Observation.API_RATE_LIMITED, Observation.API_ERROR):
            with self.subTest(value=value):
                result = policy.evaluate_official_lifecycle_policy(
                    observed(value, None)
                )
                self.assertEqual(
                    result.state, policy.EligibilityState.TEMPORARILY_BLOCKED
                )
                self.assertTrue(result.bounded_wait_required)
                self.assertTrue(result.stop_on_rate_limit)
                self.assertEqual(result.retry_attempt_limit, 1)
                self.assertEqual(result.wait_seconds_upper_bound, 300)
                self.assertTrue(result.exclude_from_public_site)
                self.assert_gates_closed(result)

    def test_preorder_and_out_of_stock_do_not_exclude_by_themselves(self):
        for signal in (
            policy.InventorySignal.PREORDER,
            policy.InventorySignal.OUT_OF_STOCK,
        ):
            with self.subTest(signal=signal):
                result = policy.evaluate_official_lifecycle_policy(
                    observed(Observation.API_ITEM_VISIBLE, True),
                    inventory_signal=signal,
                )
                self.assertEqual(result.state, policy.EligibilityState.CANDIDATE)
                self.assertTrue(result.public_listing_candidate)
                self.assertTrue(result.affiliate_candidate)
                self.assertFalse(result.exclude_from_public_site)
                self.assertTrue(result.inventory_signal_only)
                self.assertEqual(result.observation_observed_at, NOW)
                self.assert_gates_closed(result)

    def test_unknown_or_malformed_inputs_fail_closed(self):
        cases = (
            None,
            replace(
                observed(Observation.API_ITEM_VISIBLE, True),
                observation="NEW_OBSERVATION",
            ),
            replace(
                observed(Observation.API_ITEM_VISIBLE, True),
                affiliate_link_observed=1,
            ),
            replace(
                observed(Observation.API_ITEM_VISIBLE, True),
                expected_content_id_match=False,
            ),
            replace(
                observed(Observation.API_ITEM_VISIBLE, True),
                observed_at=datetime(2026, 9, 16, 6, 0),
            ),
        )
        for value in cases:
            with self.subTest(value=value):
                result = policy.evaluate_official_lifecycle_policy(value)
                self.assertEqual(result.state, policy.EligibilityState.FAIL_CLOSED)
                self.assertTrue(result.exclude_from_public_site)
                self.assertFalse(result.affiliate_candidate)
                self.assert_gates_closed(result)

    def test_policy_accepts_no_url_path_rank_offset_or_frequency_input(self):
        source = Path(policy.__file__).read_text(encoding="utf-8")
        self.assertNotIn("affiliate_url:", source)
        self.assertNotIn("source_offset", source)
        self.assertNotIn("schedule", source.lower())
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("urllib", source)

    def test_offset_fields_are_pagination_not_public_rank(self):
        self.assertEqual(
            policy.OFFSET_SEMANTICS, "PAGINATION_SEARCH_START_POSITION"
        )
        self.assertEqual(
            policy.FIRST_POSITION_SEMANTICS,
            "PAGINATION_SEARCH_START_POSITION",
        )
        result = policy.evaluate_official_lifecycle_policy(
            observed(Observation.API_ITEM_VISIBLE, True)
        )
        self.assertFalse(result.offset_rank_allowed)
        self.assertFalse(result.public_rank_number_allowed)


if __name__ == "__main__":
    unittest.main()
