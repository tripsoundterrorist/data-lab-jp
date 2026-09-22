import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "revenue-mvp-unordered-edge-reactivation-request-20260922.json"
)


class UnorderedEdgeReactivationRequestTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_prior_one_time_approval_is_consumed_and_non_reusable(self):
        self.assertEqual(
            self.value["decision"], "APPROVE_FRESH_ONE_TIME_REACTIVATION_REQUEST"
        )
        prior = self.value["prior_activation"]
        self.assertTrue(prior["prior_one_time_approval_consumed"])
        self.assertFalse(prior["prior_approval_reusable"])
        self.assertEqual(prior["rollback_state"], "CLOSED")
        self.assertEqual(prior["rollback_reason"], "EDGE_ARTIFACT_MISMATCH")

    def test_request_is_bound_to_exact_artifact_and_edge_control(self):
        source = self.value["source"]
        for name in (
            "source_packet_sha256",
            "rendered_artifact_sha256",
            "replacement_source_sha256",
        ):
            self.assertEqual(len(source[name]), 64)
            int(source[name], 16)
        self.assertEqual(source["candidate_count"], 100)
        self.assertEqual(source["target_route"], "/items/")
        self.assertEqual(
            source["replacement_source_hash_encoding"],
            "UTF-8 bytes with LF line endings, matching the Git repository blob and deployment source",
        )
        edge = self.value["edge_control"]
        self.assertEqual(edge["path_scope"], "/items/*")
        self.assertEqual(edge["required_cache_control_directive"], "no-transform")
        self.assertTrue(
            edge["read_only_production_observation"][
                "cache_control_contains_no_transform"
            ]
        )
        self.assertFalse(
            edge["read_only_production_observation"]["cloudflare_beacon_present"]
        )

    def test_fresh_approval_and_edge_hash_match_are_mandatory(self):
        approval = self.value["user_must_explicitly_approve"]
        self.assertIn(
            "CLOSED -> APPROVED_FOR_ONE_TIME_EDGE_VERIFIED_REACTIVATION",
            approval["proposed_scoped_gate_transition"],
        )
        self.assertTrue(
            any("edge response SHA-256" in value for value in approval["post_execution_requirements"])
        )
        self.assertIn("edge SHA mismatch", self.value["rollback"]["trigger"])
        self.assertIn(
            "the prior approval is reused instead of a fresh explicit approval",
            self.value["expiry_conditions"],
        )
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
        self.assertFalse(self.value["artifact_committed"])
        self.assertFalse(self.value["packet_contents_committed"])
        self.assertFalse(self.value["product_titles_committed"])


if __name__ == "__main__":
    unittest.main()
