import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from doujin_price_snapshot_candidate import (  # noqa: E402
    VERSION,
    DoujinPriceObservation,
    assess_doujin_price_snapshot,
)


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def observation(**overrides):
    values = {
        "version": VERSION,
        "content_type": "doujin",
        "observed_at": NOW,
        "current_price": 1000,
        "list_price": 2000,
        "discount_amount": 1000,
        "discount_rate": 50.0,
    }
    values.update(overrides)
    return DoujinPriceObservation(**values)


class DoujinPriceSnapshotCandidateTests(unittest.TestCase):
    def test_consistent_discount_is_review_only(self):
        result = assess_doujin_price_snapshot(observation())
        self.assertEqual(result.status, "READY_FOR_PRICE_SEMANTICS_REVIEW")
        self.assertTrue(result.normalized_price_structure_valid)
        self.assertTrue(result.current_price_fact_candidate)
        self.assertTrue(result.discount_fact_candidate)
        self.assertFalse(result.exact_source_semantics_confirmed)
        self.assertFalse(result.historical_retention_allowed)
        self.assertFalse(result.public_display_allowed)
        self.assertFalse(result.analysis_allowed)
        self.assertFalse(result.publication_gate_change_allowed)

    def test_current_price_without_list_price_is_valid_structure(self):
        result = assess_doujin_price_snapshot(
            observation(list_price=None, discount_amount=None, discount_rate=None)
        )
        self.assertTrue(result.normalized_price_structure_valid)
        self.assertTrue(result.current_price_fact_candidate)
        self.assertFalse(result.discount_fact_candidate)

    def test_all_unavailable_is_review_candidate_not_public_fact(self):
        result = assess_doujin_price_snapshot(
            observation(
                current_price=None,
                list_price=None,
                discount_amount=None,
                discount_rate=None,
            )
        )
        self.assertTrue(result.normalized_price_structure_valid)
        self.assertFalse(result.current_price_fact_candidate)
        self.assertFalse(result.public_display_allowed)

    def test_zero_list_price_uses_no_rate(self):
        result = assess_doujin_price_snapshot(
            observation(
                current_price=0,
                list_price=0,
                discount_amount=0,
                discount_rate=None,
            )
        )
        self.assertTrue(result.normalized_price_structure_valid)
        self.assertFalse(result.discount_fact_candidate)

    def test_inconsistent_price_facts_fail_closed(self):
        invalid = [
            observation(list_price=900),
            observation(discount_amount=999),
            observation(discount_rate=49.9),
            observation(list_price=None),
            observation(current_price=None),
            observation(current_price=True),
        ]
        for value in invalid:
            with self.subTest(value=value):
                result = assess_doujin_price_snapshot(value)
                self.assertEqual(result.status, "FAIL_CLOSED")
                self.assertFalse(result.public_display_allowed)

    def test_wrong_contract_scope_and_time_fail_closed(self):
        invalid = [
            {},
            observation(version="old"),
            observation(content_type="video"),
            observation(observed_at=datetime(2026, 10, 2, 12, 0)),
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(
                    assess_doujin_price_snapshot(value).status,
                    "FAIL_CLOSED",
                )

    def test_serialized_result_has_no_identity_or_raw_values(self):
        result = assess_doujin_price_snapshot(observation()).to_dict()
        self.assertFalse(
            {
                "content_id",
                "url",
                "title",
                "current_price",
                "list_price",
                "discount_amount",
                "discount_rate",
            }
            & set(result)
        )


if __name__ == "__main__":
    unittest.main()
