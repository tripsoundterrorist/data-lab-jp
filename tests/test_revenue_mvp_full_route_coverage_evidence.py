import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "evidence" / "revenue-mvp-full-route-coverage-20260930.json"


class FullRouteCoverageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(PATH.read_text(encoding="utf-8"))

    def test_current_surface_has_exact_full_runtime_coverage(self):
        self.assertEqual(self.value["status"], "VERIFIED_FULL_ROUTE_COVERAGE")
        surface = self.value["production_surface"]
        d1 = self.value["private_d1_aggregate"]
        self.assertEqual((surface["card_count"], surface["cta_count"]), (100, 100))
        self.assertEqual(d1["production_surface_candidate_count"], 100)
        for name in (
            "production_surface_lookup_matches",
            "production_surface_eligible_matches",
            "production_surface_redirect_matches",
            "production_surface_runtime_redirect_matches",
        ):
            self.assertEqual(d1[name], 100)
        self.assertFalse(d1["identifiers_exposed"])
        self.assertFalse(d1["affiliate_urls_exposed"])
        self.assertEqual(d1["rows_written_by_verification_queries"], 0)

    def test_revenue_regression_was_blocked(self):
        decision = self.value["refresh_decision"]
        self.assertEqual(decision["latest_collector_candidate_count"], 100)
        self.assertEqual(decision["latest_candidate_runtime_redirect_matches"], 83)
        self.assertEqual(decision["latest_candidate_missing_runtime_redirects"], 17)
        self.assertFalse(decision["latest_candidate_activated"])
        self.assertTrue(decision["current_surface_retained"])
        self.assertEqual(
            decision["reason_code"], "REVENUE_ROUTE_COVERAGE_REGRESSION_BLOCKED"
        )

    def test_no_publication_or_gate_change_is_claimed(self):
        self.assertFalse(self.value["publication_write_performed"])
        self.assertFalse(self.value["artifact_write_performed"])
        self.assertEqual(self.value["global_publication_gate"], "unchanged")
        self.assertFalse(self.value["paid_plan_change"])


if __name__ == "__main__":
    unittest.main()
