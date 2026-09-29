import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/revenue-mvp-minimal-opaque-go-cta-user-approval-20260929-d1-intersection.json"
APPROVED = "10aafd067419cfec813ed9614db33407833fc577fb44365bc55080df354095b9"


class D1IntersectionApprovalTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_artifact_and_d1_intersection_scope(self):
        scope = self.value["approved_scope"]
        self.assertEqual(self.value["decision"], "APPROVED")
        self.assertEqual(scope["artifact_sha256"], APPROVED)
        self.assertEqual(scope["selection_method"], "EXACT_REVIEWED_D1_INTERSECTION_ID")
        self.assertEqual(scope["d1_match_count"], 1)
        self.assertEqual(scope["maximum_cta_count"], 1)
        self.assertEqual(scope["existing_live_item_count_must_be_preserved"], 100)
        self.assertTrue(scope["opaque_public_id_only"])
        self.assertTrue(scope["proximate_pr_disclosure_required"])
        self.assertTrue(scope["free_plan_only"])

    def test_unbounded_and_unguaranteed_states_remain_closed(self):
        self.assertTrue(self.value["execution_guards"]["affiliate_outcome_not_guaranteed"])
        self.assertTrue(self.value["execution_guards"]["route_operation_smoke_required"])
        self.assertIn("unbounded D1 eligibility", self.value["not_approved"])
        self.assertIn("production execution without a fresh final candidate review", self.value["not_approved"])

    def test_no_secrets_or_provider_url(self):
        text = EVIDENCE.read_text(encoding="utf-8").casefold()
        for forbidden in ("api_id", "affiliate_id", "token", "password", "https://al."):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
