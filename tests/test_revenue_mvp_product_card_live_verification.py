from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "evidence" / "revenue-mvp-product-card-live-verification-20260929.json"


class ProductCardLiveVerificationTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(PATH.read_text(encoding="utf-8"))

    def test_evidence_is_bounded_to_exact_live_surface(self):
        self.assertEqual(self.value["status"], "VERIFIED_LIVE")
        production = self.value["production"]
        self.assertEqual(production["route"], "/items/")
        self.assertEqual(production["item_count"], 100)
        self.assertEqual(production["cta_count"], 100)
        self.assertEqual(production["proximate_pr_disclosure_count"], 100)
        self.assertEqual(self.value["private_d1"]["runtime_target_count"], 100)
        deployment = self.value["deployment"]
        self.assertTrue(deployment["first_lifecycle_run_verified"])
        self.assertIsNone(deployment["lifecycle_cron"])
        self.assertEqual(deployment["revalidation_status"], "PAUSED_TRANSPORT_INCOMPATIBLE")
        self.assertEqual(deployment["first_lifecycle_run"]["restored_count"], 5)
        self.assertEqual(self.value["global_publication_gate"], "unchanged")

    def test_evidence_does_not_expose_private_values(self):
        text = PATH.read_text(encoding="utf-8")
        for forbidden in ("affiliateURL", "DMM_API_ID", "DMM_AFFILIATE_ID", "api.dmm.com"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
