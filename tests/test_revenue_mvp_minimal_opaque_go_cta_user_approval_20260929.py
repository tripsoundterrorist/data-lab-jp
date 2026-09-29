import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/revenue-mvp-minimal-opaque-go-cta-user-approval-20260929.json"
APPROVED = "a8fa335543cfe9b737494588e0ebd53409b0c5931593c141dc3fe224eb32811e"


class MinimalOpaqueGoCtaUserApproval20260929Tests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_bounded_scope(self):
        scope = self.value["approved_scope"]
        self.assertEqual(self.value["decision"], "APPROVED")
        self.assertEqual(scope["artifact_sha256"], APPROVED)
        self.assertEqual(scope["public_route"], "/items/")
        self.assertEqual(scope["cta_route_prefix"], "/go/")
        self.assertEqual(scope["maximum_cta_count"], 1)
        self.assertEqual(scope["existing_live_item_count_must_be_preserved"], 100)
        self.assertTrue(scope["opaque_public_id_only"])
        self.assertTrue(scope["proximate_pr_disclosure_required"])
        self.assertTrue(scope["free_plan_only"])

    def test_unguaranteed_relay_and_unsafe_expansion_stay_closed(self):
        self.assertTrue(self.value["execution_guards"]["affiliate_outcome_not_guaranteed"])
        self.assertTrue(self.value["execution_guards"]["route_operation_smoke_required"])
        excluded = " ".join(self.value["not_approved"])
        for marker in ("more than one CTA", "provider URL", "global Publication Gate", "unbounded D1", "paid plan", "automatic retry", "production execution"):
            self.assertIn(marker, excluded)

    def test_no_secrets_or_provider_url(self):
        text = EVIDENCE.read_text(encoding="utf-8").casefold()
        for forbidden in ("api_id", "affiliate_id", "token", "password", "https://al."):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
