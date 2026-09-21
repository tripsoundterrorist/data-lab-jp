import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "evidence" / "revenue-mvp-unordered-scoped-activation-20260922.json"
ARTIFACT = ROOT / "items" / "index.html"


class ScopedActivationTests(unittest.TestCase):
    def test_exact_artifact_and_route_are_bound(self):
        state = json.loads(STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "APPROVED_FOR_ONE_TIME_EXACT_ARTIFACT_ACTIVATION")
        self.assertEqual(state["candidate_count"], 100)
        self.assertEqual(state["target_route"], "/items/")
        self.assertEqual(state["replacement_source"], "items/index.html")
        self.assertEqual(hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(), state["artifact_sha256"])

    def test_global_and_revenue_expansion_remain_closed(self):
        state = json.loads(STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["global_publication_gate"], "unchanged")
        self.assertFalse(state["cta_allowed"])
        self.assertFalse(state["affiliate_eligibility_allowed"])
        self.assertFalse(state["d1_write_allowed"])
        self.assertFalse(state["scope_expansion_allowed"])
        self.assertIn("CLOSED", state["rollback"])


if __name__ == "__main__":
    unittest.main()
