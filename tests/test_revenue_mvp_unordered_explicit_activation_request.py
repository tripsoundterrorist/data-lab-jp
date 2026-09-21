import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "revenue-mvp-unordered-explicit-activation-request-20260922.json"
)


class UnorderedExplicitActivationRequestTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_request_is_approvable_but_non_activating(self):
        self.assertEqual(
            self.value["decision"], "APPROVE_EXPLICIT_ACTIVATION_REQUEST"
        )
        self.assertIn("does not change", self.value["decision_boundary"])
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
        self.assertEqual(
            self.value["verified_boundary"]["global_publication_gate"], "unchanged"
        )

    def test_user_approval_is_bound_to_exact_hashes_route_and_replacement(self):
        source = self.value["source"]
        approval = self.value["user_must_explicitly_approve"]
        for name in (
            "source_packet_sha256",
            "rendered_artifact_sha256",
            "replacement_source_sha256",
        ):
            self.assertEqual(len(source[name]), 64)
            int(source[name], 16)
        self.assertEqual(source["candidate_count"], 100)
        self.assertEqual(source["target_route"], "/items/")
        self.assertEqual(source["replacement_source"], "items/index.html")
        self.assertIn(source["source_packet_sha256"], approval["exact_source_packet_sha256"])
        self.assertIn(source["rendered_artifact_sha256"], approval["exact_rendered_artifact_sha256"])
        self.assertIn(
            "CLOSED -> APPROVED_FOR_ONE_TIME_EXACT_ARTIFACT_ACTIVATION",
            approval["proposed_scoped_gate_transition"],
        )

    def test_rollback_expiry_and_scope_guards_are_mandatory(self):
        self.assertIn("return the scoped Gate to CLOSED", self.value["rollback"]["operation"])
        self.assertTrue(self.value["rollback"]["required_if_any_binding_fails"])
        self.assertIn(
            "global Publication Gate change",
            self.value["user_must_explicitly_approve"]["excluded_operations"],
        )
        self.assertIn(
            "scope expansion",
            self.value["user_must_explicitly_approve"]["excluded_operations"],
        )
        self.assertFalse(self.value["artifact_committed"])
        self.assertFalse(self.value["packet_contents_committed"])
        self.assertFalse(self.value["product_titles_committed"])


if __name__ == "__main__":
    unittest.main()
