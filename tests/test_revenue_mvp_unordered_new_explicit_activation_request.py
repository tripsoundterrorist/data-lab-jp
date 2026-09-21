import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "revenue-mvp-unordered-new-explicit-activation-request-20260922.json"
)


class UnorderedNewExplicitActivationRequestTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_new_request_approves_only_presentation_and_invalidates_old_hash(self):
        self.assertEqual(
            self.value["decision"], "APPROVE_NEW_EXPLICIT_ACTIVATION_REQUEST"
        )
        self.assertEqual(
            self.value["supersession"]["invalidating_regression_pr_state"],
            "CLOSED_UNMERGED",
        )
        self.assertEqual(
            self.value["supersession"]["invalidating_regression_validation"],
            "FAILURE",
        )
        self.assertNotEqual(
            self.value["supersession"]["invalidated_artifact_sha256"],
            self.value["source"]["rendered_artifact_sha256"],
        )

    def test_new_approval_is_bound_to_repaired_renderer_and_exact_route(self):
        source = self.value["source"]
        self.assertEqual(source["renderer_version"], "0.2-candidate")
        self.assertEqual(source["candidate_count"], 100)
        self.assertEqual(source["target_route"], "/items/")
        self.assertEqual(source["replacement_source"], "items/index.html")
        for name in (
            "source_packet_sha256",
            "rendered_artifact_sha256",
            "replacement_source_sha256",
        ):
            self.assertEqual(len(source[name]), 64)
            int(source[name], 16)
        boundary = self.value["verified_boundary"]
        self.assertTrue(boundary["allowed_existing_shell_assets_only"])
        self.assertTrue(boundary["items_js_absent"])
        self.assertTrue(boundary["product_and_affiliate_links_absent"])

    def test_all_activations_remain_closed_until_user_approval(self):
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
        self.assertIn(
            "CLOSED -> APPROVED_FOR_ONE_TIME_EXACT_ARTIFACT_ACTIVATION",
            self.value["user_must_explicitly_approve"][
                "proposed_scoped_gate_transition"
            ],
        )
        self.assertIn("return the scoped Gate to CLOSED", self.value["rollback"]["operation"])
        self.assertFalse(self.value["artifact_committed"])
        self.assertFalse(self.value["packet_contents_committed"])
        self.assertFalse(self.value["product_titles_committed"])


if __name__ == "__main__":
    unittest.main()
