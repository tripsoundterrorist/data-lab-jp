import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "evidence" / "revenue-mvp-latest-product-activation-request-20260930.json"


class LatestProductActivationRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(PATH.read_text(encoding="utf-8"))

    def test_exact_candidate_and_bounded_rotation(self):
        self.assertEqual(
            self.value["status"], "READY_FOR_EXPLICIT_PRODUCTION_APPROVAL"
        )
        scope = self.value["scope"]
        self.assertEqual(len(scope["source_artifact_sha256"]), 64)
        self.assertEqual(len(scope["candidate_artifact_sha256"]), 64)
        self.assertNotEqual(
            scope["source_artifact_sha256"], scope["candidate_artifact_sha256"]
        )
        self.assertEqual((scope["source_card_count"], scope["candidate_card_count"]), (100, 100))
        self.assertEqual((scope["retained_count"], scope["added_count"], scope["removed_count"]), (88, 12, 12))
        self.assertEqual((scope["candidate_official_image_count"], scope["candidate_cta_count"], scope["candidate_go_route_count"]), (100, 100, 100))
        self.assertTrue(scope["discovery_controls_preserved"])
        self.assertTrue(scope["robots_noindex_preserved"])
        self.assertFalse(scope["private_affiliate_url_exposed"])

    def test_candidate_has_full_private_runtime_coverage(self):
        d1 = self.value["private_d1"]
        for key in (
            "candidate_lookup_matches", "candidate_eligible_matches",
            "candidate_redirect_matches", "candidate_runtime_redirect_matches",
        ):
            self.assertEqual(d1[key], 100)
        self.assertEqual((d1["scoped_revalidation_selected"], d1["scoped_revalidation_valid"], d1["scoped_revalidation_disabled"]), (12, 12, 0))
        self.assertFalse(d1["identifiers_exposed"])
        self.assertFalse(d1["affiliate_urls_exposed"])

    def test_activation_remains_closed_until_explicit_approval(self):
        activation = self.value["activation"]
        self.assertFalse(activation["production_write_performed"])
        self.assertFalse(activation["publication_allowed"])
        self.assertTrue(activation["explicit_user_approval_required"])
        self.assertEqual(self.value["global_publication_gate"], "unchanged")
        self.assertFalse(self.value["paid_plan_change"])


if __name__ == "__main__":
    unittest.main()
