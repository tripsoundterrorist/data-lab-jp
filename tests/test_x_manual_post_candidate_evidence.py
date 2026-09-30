import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "x-manual-post-candidate-20260930.json"


class XManualPostCandidateEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_candidate_remains_manual_and_fail_closed(self):
        self.assertEqual(self.evidence["status"], "AWAITING_MANUAL_APPROVAL")
        validation = self.evidence["validation"]
        self.assertTrue(validation["pr_disclosure_present"])
        self.assertFalse(validation["product_media_used"])
        self.assertFalse(validation["direct_affiliate_link_used"])
        self.assertFalse(validation["automatic_posting_authorized"])
        self.assertFalse(self.evidence["external_write_performed"])

    def test_candidate_is_bounded_and_measurable(self):
        validation = self.evidence["validation"]
        self.assertLessEqual(validation["non_url_raw_characters"], 140)
        self.assertLessEqual(
            validation["x_weighted_length_estimate"],
            validation["x_weighted_limit"],
        )
        self.assertEqual(validation["verified_public_item_count"], 100)
        self.assertIn("utm_source=x", self.evidence["post_text"])
        self.assertIn("【PR】", self.evidence["post_text"])
        self.assertTrue(
            all(
                value == "NOT_ACQUIRED"
                for value in self.evidence["measurement_after_manual_post"].values()
            )
        )


if __name__ == "__main__":
    unittest.main()
