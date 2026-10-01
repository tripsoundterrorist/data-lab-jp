import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "runtime/evidence/revenue-mvp-live-surface-smoke-20261001.json"


class LiveSurfaceSmokeEvidenceTests(unittest.TestCase):
    def test_live_smoke_matches_current_exact_public_artifact(self):
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        digest = hashlib.sha256((ROOT / "items/index.html").read_bytes()).hexdigest()
        self.assertEqual(value["version"], "0.1")
        self.assertEqual(value["status"], "LIVE_SURFACE_SMOKE_VERIFIED")
        self.assertEqual(value["source_domain"], "datalabx.jp")
        self.assertEqual(value["items_artifact_sha256"], digest)
        self.assertTrue(value["items_artifact_exact_match"])
        self.assertEqual(value["live_item_count"], 100)
        self.assertEqual(value["affiliate_cta_count"], 100)
        self.assertEqual(value["pr_disclosure_count"], 100)
        self.assertEqual(value["image_element_count"], 100)

    def test_routes_and_indexing_remain_fail_closed(self):
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(value["homepage_http_status"], 200)
        self.assertEqual(value["items_http_status"], 200)
        self.assertEqual(value["robots_http_status"], 200)
        self.assertEqual(value["sitemap_http_status"], 200)
        self.assertEqual(value["invalid_go_route_http_status"], 404)
        self.assertTrue(value["items_noindex_nofollow_present"])
        self.assertTrue(value["items_canonical_exact"])
        self.assertEqual(value["sitemap_url_count"], 9)
        self.assertFalse(value["item_detail_in_sitemap"])
        self.assertFalse(value["go_route_in_sitemap"])
        self.assertFalse(value["valid_affiliate_route_requested"])
        self.assertFalse(value["external_write_performed"])
        self.assertFalse(value["production_change_performed"])


if __name__ == "__main__":
    unittest.main()
