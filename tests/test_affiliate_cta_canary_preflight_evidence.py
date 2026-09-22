import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "runtime" / "evidence" / "affiliate-cta-canary-preflight-20260922.json"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class AffiliateCtaCanaryPreflightEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_sanitized_counts_are_bound(self):
        self.assertEqual(self.value["status"], "CTA_CANARY_PREFLIGHT_READY_FOR_EXACT_REVIEW")
        self.assertEqual(self.value["scope"], "INITIAL_TEN_ITEM_CTA_CANARY")
        self.assertEqual(self.value["live_surface_route"], "/items/")
        for key in (
            "live_surface_artifact_sha256",
            "source_database_sha256",
            "selection_digest",
        ):
            self.assertIsNotNone(SHA256.fullmatch(self.value[key]))
        for key in (
            "submitted_count", "lookup_attempt_count", "api_request_attempt_count",
            "verified_count", "selected_count",
        ):
            self.assertEqual(self.value[key], 10)

    def test_no_sensitive_values_or_mutation_authority_are_recorded(self):
        for key in (
            "identifiers_exposed", "affiliate_urls_exposed",
            "secret_values_read_into_output", "production_write_performed",
            "cta_activation_allowed", "d1_write_allowed", "deployment_allowed",
            "paid_plan_change_allowed", "rate_limit_stop",
        ):
            self.assertFalse(self.value[key])
        serialized = json.dumps(self.value, ensure_ascii=False)
        for forbidden in ("public_id", "content_id", "affiliateURL", "api_id", "affiliate_id"):
            self.assertNotIn(forbidden, serialized)

    def test_next_action_is_review_not_activation(self):
        self.assertEqual(
            self.value["next_action"],
            "COMPLIANCE_REVIEW_EXACT_SANITIZED_CANARY",
        )


if __name__ == "__main__":
    unittest.main()

