import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/revenue-mvp-minimal-opaque-go-cta-user-approval-20260925.json"
APPROVED_ARTIFACT = "f273ec05089eabd19da50e7d62dfb2f747282f53d37f9babcb7a63c79c78dcf9"


class MinimalOpaqueGoCtaUserApprovalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_bounded_scope_is_recorded(self):
        self.assertEqual(self.value["decision"], "APPROVED")
        scope = self.value["approved_scope"]
        self.assertEqual(scope["artifact_sha256"], APPROVED_ARTIFACT)
        self.assertEqual(scope["public_route"], "/items/")
        self.assertEqual(scope["cta_route_prefix"], "/go/")
        self.assertEqual(scope["maximum_cta_count"], 1)
        self.assertEqual(scope["existing_live_item_count_must_be_preserved"], 100)
        self.assertTrue(scope["opaque_public_id_only"])
        self.assertTrue(scope["proximate_pr_disclosure_required"])
        self.assertTrue(scope["free_plan_only"])

    def test_unsafe_expansion_is_explicitly_excluded(self):
        excluded = " ".join(self.value["not_approved"])
        for marker in (
            "more than one CTA", "provider URL", "Publication Gate",
            "unbounded D1", "paid plan", "automatic retry",
        ):
            self.assertIn(marker, excluded)
        self.assertTrue(all(self.value["execution_guards"].values()))

    def test_evidence_contains_no_secret_or_provider_url(self):
        text = EVIDENCE.read_text(encoding="utf-8").casefold()
        for forbidden in (
            "api_id", "affiliate_id", "token", "password", "https://al.",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
