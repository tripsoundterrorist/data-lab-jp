from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_dry_connection_contract_review as review  # noqa: E402


class DryConnectionContractReviewTests(unittest.TestCase):
    def test_public_validated_state_handoff_is_ready(self):
        result = review.review_dry_connection_contract()
        self.assertEqual(result.status, review.CONTRACT_READY)
        self.assertTrue(result.readiness_evidence_verified)
        self.assertTrue(result.adapter_accepts_sanitized_payloads)
        self.assertTrue(result.harness_accepts_validated_states)
        self.assertTrue(result.public_validated_state_bundle_available)
        self.assertFalse(result.private_validator_dependency_allowed)
        self.assertFalse(result.duplicate_payload_validation_allowed)
        self.assertFalse(result.active_connection_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertEqual(result.next_gate, review.NEXT_GATE)

    def test_missing_public_handoff_requires_contract_change(self):
        with mock.patch.object(
            review.adapter, "build_validated_series_state_bundle",
            None,
        ):
            result = review.review_dry_connection_contract()
        self.assertEqual(result.status, review.CONTRACT_CHANGE_REQUIRED)
        self.assertIsNone(result.next_gate)
        self.assertFalse(result.active_connection_authorized)

    def test_introspection_failure_does_not_leak_details(self):
        with mock.patch.object(
            review.inspect, "signature",
            side_effect=RuntimeError("secret source path"),
        ):
            result = review.review_dry_connection_contract()
        encoded = json.dumps(result.to_dict())
        self.assertEqual(result.status, review.FAIL_CLOSED)
        self.assertNotIn("secret", encoded)

    def test_source_has_no_active_filesystem_or_external_io(self):
        source = Path(review.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "run_series_integration_dry_run(", "run_dry_connection_harness(",
            "run_temporal_probe(", "write_temporal_probe_state(", "open(",
            "read_text(", "read_bytes(", "write_text(", "write_bytes(",
            "mkdir(", "unlink(", "urllib", "requests", "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
