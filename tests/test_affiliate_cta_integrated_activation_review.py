import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "affiliate-cta-integrated-activation-review-20260922.json"


class AffiliateCtaIntegratedActivationReviewTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_block_decision_is_bound_to_the_integrated_main_revision(self):
        self.assertEqual(self.value["decision"], "BLOCK_ACTIVATION_REQUEST_PRESENTATION")
        self.assertEqual(
            self.value["reviewed_main_commit"],
            "ef4d8d06fc296142263dec19c92d83c28976a465",
        )
        self.assertEqual(
            self.value["reviewed_prs"]["282"]["merge_commit"],
            "9c24d38d204c864f59ef46d79d7281f902c1f019",
        )
        self.assertEqual(
            self.value["reviewed_prs"]["283"]["merge_commit"],
            "635f0b5071dd34970b36bbf0f948edbad6218f91",
        )
        self.assertEqual(
            self.value["reviewed_prs"]["284"]["merge_commit"],
            "ef4d8d06fc296142263dec19c92d83c28976a465",
        )

    def test_evidence_remains_fail_closed_and_does_not_expose_a_url(self):
        controls = self.value["reviewed_controls"]
        self.assertTrue(controls["fail_closed_required"])
        self.assertFalse(controls["affiliate_url_exposed_in_evidence"])
        self.assertTrue(all(not value for value in controls["activation_flags"].values()))
        self.assertEqual(
            {blocker["code"] for blocker in self.value["blockers"]},
            {
                "EXACT_SELECTION_NOT_CRYPTOGRAPHICALLY_BOUND",
                "CLICK_REVALIDATION_NOT_BOUND_TO_CLICKED_ITEM",
                "REQUIRED_LINK_REL_TOKENS_MISSING",
            },
        )


if __name__ == "__main__":
    unittest.main()
