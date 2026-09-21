import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "revenue-mvp-unordered-review-packet-20260922.json"


class UnorderedReviewPacketEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_evidence_is_sanitized_and_anchors_the_reviewed_packet(self):
        self.assertEqual(self.value["decision"], "MANUAL_REVIEW_PACKET_APPROVED")
        self.assertEqual(
            self.value["source"]["origin_main_commit"],
            "f6652e7f62943ed903204efc96c4a33a68b391dc",
        )
        packet_hash = self.value["source"]["packet_sha256"]
        self.assertEqual(len(packet_hash), 64)
        int(packet_hash, 16)
        self.assertEqual(self.value["source"]["candidate_count"], 100)
        self.assertEqual(self.value["source"]["contract_version"], "0.1")
        self.assertFalse(self.value["packet_contents_committed"])
        self.assertFalse(self.value["product_titles_committed"])

    def test_scope_has_only_the_bounded_contract_and_no_public_order_claim(self):
        self.assertEqual(
            set(self.value["allowed_scope"]["fields"]),
            {
                "title",
                "api_observed_at",
                "transparency_notice",
                "current_price",
                "price_observed_at",
            },
        )
        self.assertIn(
            "not a public order claim",
            self.value["allowed_scope"]["unordered_serialization"],
        )
        self.assertIn(
            "rank_order_offset_or_source_sort",
            self.value["forbidden_scope"],
        )
        self.assertIn("url_or_affiliate_value", self.value["forbidden_scope"])
        self.assertTrue(self.value["validation"]["all_candidate_schemas_exactly_allowed"])
        self.assertEqual(self.value["validation"]["stale_over_24h_count"], 0)
        self.assertEqual(self.value["validation"]["future_observation_count"], 0)

    def test_activation_and_remaining_gates_stay_closed(self):
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
        self.assertIn(
            "MANUAL_PUBLICATION_GATE_PASS_REQUIRED",
            self.value["remaining_blockers"],
        )
        self.assertIn(
            "NO_LIVE_ROUTE_OR_DEPLOYMENT_AUTHORIZATION",
            self.value["remaining_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
