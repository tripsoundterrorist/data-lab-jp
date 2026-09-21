import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "revenue-mvp-unordered-reduced-surface-gate-decision-20260922.json"
)


class UnorderedReducedSurfaceGateDecisionTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_decision_is_blocked_only_by_production_readiness(self):
        self.assertEqual(self.value["decision"], "BLOCK")
        gates = self.value["required_gate_assessment"]
        for name in (
            "RIGHTS_GATE",
            "LIFECYCLE_GATE",
            "SEMANTICS_GATE",
            "DATA_POLICY_GATE",
            "ARTIFACT_MANUAL_REVIEW_GATE",
        ):
            self.assertEqual(gates[name]["status"], "PASS_FOR_EXACT_SCOPE")
        self.assertEqual(gates["PRODUCTION_READINESS_GATE"]["status"], "BLOCK")

    def test_scope_is_bounded_and_unresolved_topics_cannot_expand_it(self):
        self.assertEqual(
            set(self.value["exact_scope"]["allowed_fields"]),
            {
                "title",
                "api_observed_at",
                "transparency_notice",
                "current_price",
                "price_observed_at",
            },
        )
        self.assertIn(
            "rank_order_offset_source_sort_or_review",
            self.value["excluded_scope"],
        )
        self.assertTrue(
            self.value["unresolved_official_topics"]["still_block_expanded_scope"]
        )
        self.assertTrue(
            self.value["unresolved_official_topics"][
                "new_official_query_required_before_expansion"
            ]
        )

    def test_gate_mutation_and_every_activation_stay_closed(self):
        self.assertEqual(
            self.value["activation"],
            {
                "publication_allowed": False,
                "production_activation_allowed": False,
                "affiliate_eligibility_allowed": False,
                "gate_mutation_allowed": False,
                "cta_allowed": False,
            },
        )
        self.assertEqual(
            self.value["rollback"]["global_publication_gate"], "unchanged"
        )
        self.assertFalse(self.value["packet_contents_committed"])
        self.assertFalse(self.value["product_titles_committed"])


if __name__ == "__main__":
    unittest.main()
