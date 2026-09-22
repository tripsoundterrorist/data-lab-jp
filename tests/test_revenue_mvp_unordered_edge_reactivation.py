import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "evidence" / "revenue-mvp-unordered-edge-reactivation-20260922.json"
ARTIFACT = ROOT / "items" / "index.html"

class EdgeReactivationTests(unittest.TestCase):
    def setUp(self):
        self.state = json.loads(STATE.read_text(encoding="utf-8"))

    def test_exact_artifact_is_pending_edge_verification(self):
        self.assertEqual(self.state["state"], "APPROVED_FOR_ONE_TIME_EDGE_VERIFIED_REACTIVATION")
        self.assertEqual(self.state["activation_result"], "PENDING_EDGE_VERIFICATION")
        self.assertEqual(hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(), self.state["artifact_sha256"])
        self.assertEqual(self.state["candidate_count"], 100)
        self.assertEqual(self.state["target_route"], "/items/")
        self.assertTrue(self.state["edge_no_transform_verified_before_activation"])
        self.assertTrue(self.state["post_deployment_edge_sha_required"])

    def test_expansion_remains_closed(self):
        self.assertEqual(self.state["global_publication_gate"], "unchanged")
        for key in ("cta_allowed", "affiliate_eligibility_allowed", "d1_write_allowed", "scope_expansion_allowed"):
            self.assertFalse(self.state[key])
        self.assertIn("CLOSED", self.state["rollback"])

if __name__ == "__main__":
    unittest.main()
