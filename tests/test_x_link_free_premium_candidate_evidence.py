import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_x_link_free_candidate as gate  # noqa: E402


class LinkFreePremiumCandidateEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "docs" / "evidence" / "x-link-free-premium-candidate-20261001.json"
        cls.value = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_evidence_reproduces_the_pure_gate_result(self):
        result = gate.build_candidate(
            fact_text=self.value["candidate_text"],
            theme=self.value["theme"],
            source_ids=self.value["source_ids"],
            source_checked_at=self.value["observed_at"],
        )
        self.assertEqual(result.status, self.value["status"])
        self.assertEqual(result.weighted_length, self.value["weighted_length"])
        self.assertEqual(list(result.reason_codes), self.value["reason_codes"])

    def test_candidate_is_link_free_non_posting_and_non_promotional(self):
        text = self.value["candidate_text"]
        for forbidden in ("http", "【PR】", "アフィリエイト", "購入"):
            self.assertNotIn(forbidden, text)
        self.assertFalse(self.value["link_included"])
        self.assertFalse(self.value["affiliate_promotion_allowed"])
        self.assertFalse(self.value["manual_post_candidate"])
        self.assertFalse(self.value["posting_performed"])
        self.assertFalse(self.value["automatic_post_allowed"])

    def test_claim_matches_sanitized_current_state(self):
        state = self.value["verified_current_state"]
        self.assertEqual(state["live_item_count"], 100)
        self.assertTrue(state["limited_surface_live"])
        self.assertIn("100作品", self.value["candidate_text"])


if __name__ == "__main__":
    unittest.main()
