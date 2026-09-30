import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "revenue-mvp-catalog-data-coverage-20261001.json"


class CatalogDataCoverageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_counts_are_internally_consistent(self):
        coverage = self.value["coverage"]
        self.assertEqual(coverage["items"], coverage["distinct_items_with_snapshots"])
        self.assertEqual(coverage["snapshots"], coverage["price_non_null_snapshots"])
        self.assertEqual(
            coverage["snapshots"],
            sum(coverage["source_sort_snapshot_counts"].values()),
        )
        self.assertLessEqual(coverage["items_with_at_least_7_snapshots"], coverage["items"])
        self.assertLessEqual(coverage["items_with_multiple_snapshots"], coverage["items"])

    def test_absent_data_blocks_unsupported_revenue_claims(self):
        coverage = self.value["coverage"]
        self.assertEqual(coverage["items_with_observed_price_change"], 0)
        self.assertEqual(coverage["review_average_non_null_snapshots"], 0)
        self.assertEqual(coverage["review_count_non_null_snapshots"], 0)
        for claim in (
            "PRICE_DROP_OR_DISCOUNT_FROM_HISTORY",
            "REVIEW_RANKING",
            "POPULARITY_RANKING",
            "OFFICIAL_RANKING",
        ):
            self.assertIn(claim, self.value["blocked_claims"])

    def test_only_deterministic_price_and_observation_discovery_is_allowed(self):
        self.assertEqual(
            set(self.value["allowed_current_uses"]),
            {
                "PRICE_ASCENDING_SORT",
                "PRICE_DESCENDING_SORT",
                "PRICE_BAND_FILTER",
                "OBSERVATION_TIME_SORT",
            },
        )
        self.assertEqual(
            self.value["next_action"],
            "USE_PRICE_DISCOVERY_WHILE_WAITING_FOR_CLOSED_PRODUCT_CLICK_DATA",
        )

    def test_audit_performed_no_mutation(self):
        for field in (
            "publication_change_performed",
            "production_write_performed",
            "database_write_performed",
            "external_write_performed",
        ):
            self.assertFalse(self.value[field])


if __name__ == "__main__":
    unittest.main()
