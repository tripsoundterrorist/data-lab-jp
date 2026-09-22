import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "evidence" / "revenue-mvp-unordered-scoped-activation-v02-20260922.json"
ARTIFACT = ROOT / "items" / "index.html"

class ScopedActivationV02Tests(unittest.TestCase):
    def setUp(self):
        self.state = json.loads(STATE.read_text(encoding="utf-8"))

    def test_exact_superseding_artifact_is_bound(self):
        self.assertEqual(self.state["state"], "CLOSED")
        self.assertEqual(self.state["activation_result"], "ROLLED_BACK_EDGE_ARTIFACT_MISMATCH")
        self.assertEqual(self.state["candidate_count"], 100)
        self.assertEqual(self.state["target_route"], "/items/")
        self.assertEqual(len(self.state["replacement_source_restored_repository_sha256"]), 64)
        int(self.state["replacement_source_restored_repository_sha256"], 16)
        self.assertNotEqual(self.state["artifact_sha256"], self.state["supersedes_artifact_sha256"])

    def test_expansion_remains_closed(self):
        self.assertEqual(self.state["global_publication_gate"], "unchanged")
        for key in ("cta_allowed", "affiliate_eligibility_allowed", "d1_write_allowed", "scope_expansion_allowed"):
            self.assertFalse(self.state[key])
        self.assertIn("CLOSED", self.state["rollback"])
        self.assertEqual(len(self.state["edge_observed_sha256"]), 64)

if __name__ == "__main__":
    unittest.main()
