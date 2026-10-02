import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from doujin_lifecycle_candidate import (  # noqa: E402
    ADAPTER_VERSION,
    DoujinLifecycleObservation,
    evaluate_doujin_lifecycle_candidate,
)
from product_verification import Observation  # noqa: E402
from revenue_mvp_official_lifecycle_policy import InventorySignal  # noqa: E402


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def observation(**overrides):
    values = {
        "version": ADAPTER_VERSION,
        "content_type": "doujin",
        "observation": Observation.API_ITEM_VISIBLE,
        "observed_at": NOW,
        "expected_content_id_match": True,
        "affiliate_link_observed": True,
        "inventory_signal": InventorySignal.UNKNOWN,
        "reason_codes": ("SANITIZED_TEST_FACT",),
    }
    values.update(overrides)
    return DoujinLifecycleObservation(**values)


class DoujinLifecycleCandidateTests(unittest.TestCase):
    def test_visible_item_is_scope_review_only_even_when_preorder(self):
        result = evaluate_doujin_lifecycle_candidate(
            observation(inventory_signal=InventorySignal.PREORDER)
        )
        self.assertEqual(result.status, "READY_FOR_EXACT_DOUJIN_SCOPE_REVIEW")
        self.assertTrue(result.underlying_lifecycle_candidate)
        self.assertFalse(result.exact_doujin_source_scope_confirmed)
        self.assertFalse(result.public_listing_candidate)
        self.assertFalse(result.affiliate_candidate)
        self.assertFalse(result.publication_gate_change_allowed)

    def test_item_not_returned_is_excluded(self):
        result = evaluate_doujin_lifecycle_candidate(
            observation(
                observation=Observation.API_ITEM_NOT_RETURNED,
                expected_content_id_match=False,
                affiliate_link_observed=None,
            )
        )
        self.assertEqual(result.status, "EXCLUDED")
        self.assertTrue(result.exclude_from_public_site)

    def test_missing_affiliate_link_is_excluded(self):
        result = evaluate_doujin_lifecycle_candidate(
            observation(affiliate_link_observed=None)
        )
        self.assertEqual(result.status, "EXCLUDED")
        self.assertFalse(result.affiliate_candidate)

    def test_rate_limit_is_bounded_and_temporarily_blocked(self):
        result = evaluate_doujin_lifecycle_candidate(
            observation(
                observation=Observation.API_RATE_LIMITED,
                expected_content_id_match=None,
                affiliate_link_observed=None,
            )
        )
        self.assertEqual(result.status, "TEMPORARILY_BLOCKED")
        self.assertTrue(result.bounded_wait_required)
        self.assertEqual(result.retry_attempt_limit, 1)
        self.assertEqual(result.wait_seconds_upper_bound, 300)

    def test_invalid_contracts_fail_closed(self):
        invalid_values = [
            {},
            observation(version="old"),
            observation(content_type="video"),
            observation(observed_at=datetime(2026, 10, 2, 12, 0)),
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                result = evaluate_doujin_lifecycle_candidate(value)
                self.assertEqual(result.status, "FAIL_CLOSED")
                self.assertFalse(result.public_listing_candidate)
                self.assertFalse(result.affiliate_candidate)

    def test_serialized_result_contains_no_source_identifier_or_url(self):
        result = evaluate_doujin_lifecycle_candidate(observation()).to_dict()
        self.assertFalse(
            {"content_id", "url", "affiliate_url", "title"} & set(result)
        )


if __name__ == "__main__":
    unittest.main()
