import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "runtime/evidence/revenue-mvp-public-revenue-health-20261002.json"


class PublicRevenueHealthEvidenceTests(unittest.TestCase):
    def test_observation_is_aggregate_and_bound_to_current_artifact(self):
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        digest = hashlib.sha256((ROOT / "items/index.html").read_bytes()).hexdigest()
        self.assertEqual(value["version"], "0.1")
        self.assertEqual(value["status"], "PUBLIC_REVENUE_SURFACE_HEALTHY")
        self.assertEqual(value["source_domain"], "datalabx.jp")
        self.assertEqual(value["items_artifact_sha256"], digest)
        self.assertNotIn("item_id", value)
        self.assertNotIn("affiliate_url", value)

    def test_all_live_ctas_and_images_pass_without_redirect_follow(self):
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(value["items_http_status"], 200)
        self.assertEqual(value["published_cta_count"], 100)
        self.assertEqual(value["redirect_http_302_count"], 100)
        self.assertEqual(value["redirect_failure_count"], 0)
        self.assertTrue(value["destination_host_verified"])
        self.assertEqual(value["published_image_count"], 100)
        self.assertEqual(value["healthy_image_count"], 100)
        self.assertEqual(value["image_failure_count"], 0)
        self.assertTrue(value["official_image_host_verified"])
        self.assertFalse(value["valid_affiliate_redirect_followed"])
        self.assertFalse(value["external_write_performed"])
        self.assertFalse(value["production_change_performed"])


if __name__ == "__main__":
    unittest.main()
