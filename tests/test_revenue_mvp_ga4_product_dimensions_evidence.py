import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "revenue-mvp-ga4-product-dimensions-20261001.json"


class RevenueMvpGa4ProductDimensionsEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_bounded_dimensions_are_recorded(self):
        self.assertEqual(
            self.value["status"],
            "GA4_PRODUCT_FUNNEL_DIMENSIONS_REGISTERED",
        )
        self.assertEqual(
            {
                (row["display_name"], row["scope"], row["event_parameter"])
                for row in self.value["custom_dimensions"]
            },
            {
                ("Funnel Surface", "EVENT", "funnel_surface"),
                ("Item ID", "EVENT", "item_id"),
            },
        )

    def test_owner_change_and_reporting_boundary_are_explicit(self):
        self.assertTrue(self.value["ga4_change_performed_by_owner"])
        self.assertFalse(self.value["production_site_write_performed"])
        self.assertFalse(self.value["retroactive"])
        self.assertEqual(self.value["expected_reporting_delay"], "24_TO_48_HOURS")
        self.assertEqual(self.value["site_collection_commit"], "382d01e")


if __name__ == "__main__":
    unittest.main()
