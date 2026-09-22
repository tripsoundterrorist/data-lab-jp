import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/affiliate-cta-integrated-activation-rereview-pr286-20260922.json"


class IntegratedActivationRereviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_review_preserves_prior_evidence_and_exact_selection_reference(self):
        prior = json.loads((ROOT / self.review["prior_review"]).read_text(encoding="utf-8"))
        conditions = json.loads((ROOT / self.review["required_conditions_source"]).read_text(encoding="utf-8"))
        self.assertEqual(self.review["reviewed_main_commit"], "0381d7ec193394c83670950052b957f60780f82d")
        self.assertNotEqual(prior["reviewed_main_commit"], self.review["reviewed_main_commit"])
        self.assertEqual(self.review["approved_selection_reference_digest"], conditions["selection_digest"])
        self.assertEqual(
            {item["code"] for item in prior["blockers"]},
            {item["code"] for item in self.review["prior_blocker_assessments"]},
        )

    def test_partial_resolution_cannot_grant_presentation_or_activation(self):
        resolutions = {item["code"]: item["resolution"] for item in self.review["prior_blocker_assessments"]}
        self.assertEqual(resolutions["REQUIRED_LINK_REL_TOKENS_MISSING"], "RESOLVED")
        self.assertEqual(resolutions["EXACT_SELECTION_NOT_CRYPTOGRAPHICALLY_BOUND"], "PARTIAL")
        self.assertEqual(resolutions["CLICK_REVALIDATION_NOT_BOUND_TO_CLICKED_ITEM"], "PARTIAL")
        self.assertEqual(self.review["decision"], "BLOCK_ACTIVATION_REQUEST_PRESENTATION")
        self.assertTrue(self.review["approval_boundary"])
        for name, value in self.review["approval_boundary"].items():
            self.assertIs(value, False, name)

    def test_observations_do_not_claim_live_verification_or_leak_destinations(self):
        checks = self.review["offline_validation"]
        self.assertFalse(checks["live_api_requests_performed"])
        self.assertFalse(checks["real_identifiers_or_affiliate_urls_recorded"])
        self.assertEqual(self.review["controls"]["render_and_click_freshness"]["maximum_age_seconds"], 900)
        self.assertEqual(self.review["controls"]["fresh_api_before_render"]["status"], "UNCONFIRMED")
        serialized = json.dumps(self.review, ensure_ascii=False)
        self.assertNotRegex(serialized, r"https?://|itm_[0-9a-f]{24}")


if __name__ == "__main__":
    unittest.main()
