import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_compliance_decision as subject  # noqa: E402


def ready_packet():
    return {
        "version": "0.1",
        "status": "READY_FOR_MANUAL_COMPLIANCE_DECISION",
        "target_item_count": 300,
        "official_lifecycle_core_confirmed": True,
        "candidate_lookup_ready_count": 300,
        "candidate_redirect_ready_count": 300,
        "candidate_runtime_ready_count": 300,
        "presentation_policy_verified": True,
        "product_funnel_window_closed": True,
        "compliance_publication_confirmed": False,
        "publication_allowed": False,
        "production_write_allowed": False,
        "reason_codes": [],
        "required_manual_checks": [],
    }


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def receipt(packet_bytes):
    return {
        "version": "0.1",
        "decision": "CONFIRM_EXPANSION_COMPLIANCE",
        "decided_at": "2026-10-10T12:00:00+09:00",
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "reviewer_role": "DATA_LAB_OWNER",
    }


class ExpansionComplianceDecisionTests(unittest.TestCase):
    def test_ready_hash_pinned_packet_can_be_confirmed_without_authorizing_changes(self):
        packet_bytes = encode(ready_packet())
        result = subject.validate(packet_bytes, receipt(packet_bytes))
        self.assertEqual(result.status, subject.CONFIRMED)
        self.assertTrue(result.compliance_publication_confirmed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.deployment_allowed)

    def test_current_blocked_packet_cannot_be_confirmed(self):
        packet_bytes = (
            ROOT / "runtime/evidence/revenue-mvp-expansion-compliance-packet-20261001.json"
        ).read_bytes()
        result = subject.validate(packet_bytes, receipt(packet_bytes))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("PACKET_NOT_READY_FOR_DECISION", result.reason_codes)

    def test_hash_mismatch_and_nonconfirmation_block(self):
        packet_bytes = encode(ready_packet())
        wrong_hash = receipt(packet_bytes); wrong_hash["packet_sha256"] = "0" * 64
        rejected = receipt(packet_bytes); rejected["decision"] = "BLOCK"
        self.assertIn(
            "PACKET_HASH_MISMATCH",
            subject.validate(packet_bytes, wrong_hash).reason_codes,
        )
        self.assertIn(
            "DECISION_NOT_CONFIRMED",
            subject.validate(packet_bytes, rejected).reason_codes,
        )

    def test_permissive_or_malformed_packet_fails_closed(self):
        value = ready_packet(); value["publication_allowed"] = True
        packet_bytes = encode(value)
        self.assertEqual(
            subject.validate(packet_bytes, receipt(packet_bytes)).status,
            subject.BLOCKED,
        )
        self.assertEqual(subject.validate(None, {}).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
