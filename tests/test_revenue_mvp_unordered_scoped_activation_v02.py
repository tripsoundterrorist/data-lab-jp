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
        self.assertEqual(self.state["state"], "APPROVED_FOR_ONE_TIME_EXACT_ARTIFACT_ACTIVATION")
        self.assertEqual(self.state["candidate_count"], 100)
        self.assertEqual(self.state["target_route"], "/items/")
        self.assertEqual(hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(), self.state["artifact_sha256"])
        self.assertNotEqual(self.state["artifact_sha256"], self.state["supersedes_artifact_sha256"])

    def test_expansion_remains_closed(self):
        self.assertEqual(self.state["global_publication_gate"], "unchanged")
        for key in ("cta_allowed", "affiliate_eligibility_allowed", "d1_write_allowed", "scope_expansion_allowed"):
            self.assertFalse(self.state[key])
        self.assertIn("CLOSED", self.state["rollback"])

if __name__ == "__main__":
    unittest.main()
