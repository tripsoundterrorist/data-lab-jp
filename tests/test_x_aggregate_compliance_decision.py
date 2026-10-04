import hashlib
import json
from pathlib import Path
import unittest

from scripts import x_aggregate_compliance_decision as decision


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "docs" / "evidence" / "x-aggregate-candidate-batch-20261004.json"
OBSERVATION = (
    ROOT / "docs" / "evidence" / "x-aggregate-official-policy-observation-20261004.json"
)


def receipt(packet_bytes: bytes) -> dict:
    finding = {
        "status": "BLOCKED",
        "source_url": "https://help.x.com/example",
        "reviewed_at": "2026-10-04T12:00:00+09:00",
    }
    return {
        "version": "0.1",
        "decision": "RECORD_X_AGGREGATE_COMPLIANCE_DECISIONS",
        "decided_at": "2026-10-04T12:00:00+09:00",
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "reviewer_role": "03_COMPLIANCE",
        "findings": {key: dict(finding) for key in decision.FINDING_KEYS},
    }


class XAggregateComplianceDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet_bytes = PACKET.read_bytes()

    def test_records_independent_findings_without_authorizing_actions(self) -> None:
        value = receipt(self.packet_bytes)
        value["findings"]["TEXT_AGGREGATE_ALLOWED"]["status"] = "ALLOWED"
        result = decision.validate(self.packet_bytes, value)
        self.assertEqual(result.status, decision.RECORDED)
        self.assertEqual(result.findings["TEXT_AGGREGATE_ALLOWED"], "ALLOWED")
        self.assertFalse(result.posting_allowed)
        self.assertFalse(result.external_send_allowed)
        self.assertFalse(result.profile_change_allowed)

    def test_rejects_packet_hash_mismatch(self) -> None:
        value = receipt(self.packet_bytes)
        value["packet_sha256"] = "0" * 64
        result = decision.validate(self.packet_bytes, value)
        self.assertEqual(result.status, decision.BLOCKED)
        self.assertIn("PACKET_HASH_MISMATCH", result.reason_codes)

    def test_rejects_missing_finding(self) -> None:
        value = receipt(self.packet_bytes)
        value["findings"].pop("POST_LINK_ALLOWED")
        result = decision.validate(self.packet_bytes, value)
        self.assertEqual(result.status, decision.BLOCKED)
        self.assertIn("FINDINGS_SCHEMA_INVALID", result.reason_codes)

    def test_rejects_unreviewed_status(self) -> None:
        value = receipt(self.packet_bytes)
        value["findings"]["BRAND_CHART_ALLOWED"]["status"] = "UNCONFIRMED"
        result = decision.validate(self.packet_bytes, value)
        self.assertEqual(result.status, decision.BLOCKED)
        self.assertIn("BRAND_CHART_ALLOWED_STATUS_INVALID", result.reason_codes)

    def test_rejects_non_https_source(self) -> None:
        value = receipt(self.packet_bytes)
        value["findings"]["POST_LINK_ALLOWED"]["source_url"] = "file:///policy"
        result = decision.validate(self.packet_bytes, value)
        self.assertEqual(result.status, decision.BLOCKED)
        self.assertIn("POST_LINK_ALLOWED_SOURCE_INVALID", result.reason_codes)

    def test_policy_observation_is_hash_bound_and_fail_closed(self) -> None:
        observation = json.loads(OBSERVATION.read_text(encoding="utf-8"))
        self.assertEqual(
            observation["packet_sha256"],
            hashlib.sha256(self.packet_bytes).hexdigest(),
        )
        self.assertEqual(
            set(observation["review_questions"]),
            decision.FINDING_KEYS,
        )
        self.assertFalse(observation["compliance_approved"])
        self.assertFalse(observation["posting_allowed"])
        self.assertFalse(observation["external_send_allowed"])
        self.assertFalse(observation["profile_change_allowed"])


if __name__ == "__main__":
    unittest.main()
