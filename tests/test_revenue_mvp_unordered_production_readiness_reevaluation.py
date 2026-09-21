import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "revenue-mvp-unordered-production-readiness-reevaluation-20260922.json"
)


class UnorderedProductionReadinessReevaluationTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_block_is_precisely_scoped_to_missing_artifact_and_deployment_checks(self):
        self.assertEqual(
            self.value["decision"],
            "BLOCK:RENDERED_ARTIFACT_VALIDATION_AND_DEPLOYMENT_PREFLIGHT_INCOMPLETE",
        )
        self.assertEqual(self.value["current_preflight"]["status"], "SHELL_VALIDATED")
        self.assertEqual(
            self.value["current_preflight"]["deployment_preflight"],
            "NOT_EVALUATED_NO_PUBLIC_DATA",
        )
        self.assertFalse(
            self.value["current_preflight"]["public_data_deployment_allowed"]
        )
        self.assertEqual(
            self.value["explicit_activation_request_candidate"]["status"],
            "NOT_READY",
        )

    def test_receipt_binding_and_non_activation_boundary_are_recorded(self):
        source = self.value["source"]
        for name in ("source_packet_sha256", "rendered_artifact_sha256"):
            self.assertEqual(len(source[name]), 64)
            int(source[name], 16)
        self.assertEqual(source["candidate_count"], 100)
        self.assertEqual(source["proposed_target_route"], "/items/")
        self.assertEqual(
            self.value["activation"],
            {
                "publication_allowed": False,
                "production_activation_allowed": False,
                "affiliate_eligibility_allowed": False,
                "gate_mutation_allowed": False,
                "cta_allowed": False,
                "public_data_deployment_allowed": False,
            },
        )
        self.assertFalse(self.value["packet_contents_committed"])
        self.assertFalse(self.value["product_titles_committed"])

    def test_safe_next_work_cannot_activate_or_deploy(self):
        self.assertIn(
            "implement_and_test_a_pure_offline_rendered_artifact_validator",
            self.value["safe_before_explicit_user_approval"],
        )
        self.assertIn(
            "change_any_gate_value",
            self.value["not_safe_without_explicit_user_approval"],
        )
        self.assertIn(
            "deploy_or_promote_any_artifact",
            self.value["not_safe_without_explicit_user_approval"],
        )


if __name__ == "__main__":
    unittest.main()
