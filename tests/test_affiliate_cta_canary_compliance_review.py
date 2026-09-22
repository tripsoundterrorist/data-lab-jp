import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "affiliate-cta-canary-compliance-review-20260922.json"


class AffiliateCtaCanaryComplianceReviewTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_decision_only_allows_presenting_exact_request(self):
        self.assertEqual(
            self.value["decision"],
            "APPROVE_EXACT_CANARY_ACTIVATION_REQUEST_PRESENTATION",
        )
        self.assertEqual(self.value["reviewed_preflight_pr"], 280)
        self.assertEqual(self.value["verified_count"], 10)
        self.assertEqual(len(self.value["selection_digest"]), 64)
        boundary = self.value["approval_boundary"]
        self.assertTrue(boundary["activation_request_presentation_allowed"])
        for key, allowed in boundary.items():
            if key != "activation_request_presentation_allowed":
                self.assertFalse(allowed, key)

    def test_revalidation_and_disclosure_are_mandatory(self):
        required = set(self.value["required_conditions"])
        self.assertIn("FRESH_API_REVALIDATION_BEFORE_RENDER_ELIGIBILITY", required)
        self.assertIn("CLICK_TIME_EXACT_ITEM_AND_AFFILIATE_URL_REVALIDATION", required)
        self.assertIn(
            "STALE_MISSING_ERROR_OR_RATE_LIMIT_STATE_HIDES_CTA_AND_BLOCKS_REDIRECT",
            required,
        )
        self.assertIn("FIXED_CTA_LABEL_AND_PROXIMATE_PR_DISCLOSURE", required)
        self.assertIn("EXPLICIT_USER_ACTIVATION_APPROVAL_REQUIRED", required)

    def test_no_sensitive_or_product_values_are_recorded(self):
        serialized = json.dumps(self.value, ensure_ascii=False)
        for forbidden in (
            "public_id", "content_id", "affiliateURL", "DMM_API_ID",
            "DMM_AFFILIATE_ID", "title",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()

