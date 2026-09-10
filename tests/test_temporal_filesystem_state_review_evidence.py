from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_filesystem_state_connection_review as review  # noqa: E402
import temporal_filesystem_state_review_evidence as evidence  # noqa: E402


class FilesystemStateReviewEvidenceTests(unittest.TestCase):
    def test_current_public_contracts_complete_review_without_authorizing_io(self):
        facts = evidence.collect_filesystem_state_review_evidence()
        self.assertTrue(facts.prerequisites_verified)
        self.assertTrue(facts.secret_pii_controls_verified)
        self.assertTrue(facts.publication_compliance_separation_verified)
        self.assertTrue(facts.explicit_approval_point_defined)
        self.assertTrue(facts.trust_boundary_verified)
        self.assertTrue(facts.rollback_recovery_verified)
        self.assertTrue(facts.idempotency_verified)
        self.assertTrue(facts.rate_cost_bounds_verified)
        self.assertFalse(facts.explicit_approval_granted)

        result = evidence.assess_current_filesystem_state_review()
        self.assertEqual(result.status, review.REVIEW_READY_FOR_EXPLICIT_APPROVAL)
        self.assertEqual(result.unmet_areas, ())
        self.assertFalse(result.connection_authorized)
        self.assertFalse(result.write_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_changed_public_contract_fails_closed(self):
        with mock.patch.object(evidence.store, "STORE_CANDIDATE_VERSION", "unknown"):
            facts = evidence.collect_filesystem_state_review_evidence()
        self.assertFalse(facts.prerequisites_verified)
        result = review.review_filesystem_state_connection(facts)
        self.assertEqual(result.status, review.REVIEW_BLOCKED)
        self.assertIn("PREREQUISITES", result.unmet_areas)

    def test_introspection_error_fails_all_evidence_closed(self):
        with mock.patch.object(evidence.inspect, "signature", side_effect=RuntimeError("secret")):
            facts = evidence.collect_filesystem_state_review_evidence()
        values = vars(facts)
        booleans = tuple(value for value in values.values() if type(value) is bool)
        self.assertTrue(booleans)
        self.assertTrue(all(value is False for value in booleans))
        self.assertNotIn("secret", json.dumps(
            review.review_filesystem_state_connection(facts).to_dict()
        ))

    def test_cli_reports_blocked_and_next_minimum_gate(self):
        result = subprocess.run(
            [sys.executable, str(Path(evidence.__file__))],
            capture_output=True, text=True, check=False,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["status"], review.REVIEW_READY_FOR_EXPLICIT_APPROVAL)
        self.assertEqual(
            payload["next_minimum_gate"], evidence.NEXT_MINIMUM_GATE
        )
        self.assertFalse(payload["write_authorized"])

    def test_source_has_no_target_calls_or_filesystem_and_network_io(self):
        source = Path(evidence.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "read_bytes(", "write_text(",
            "write_bytes(", "mkdir(", "unlink(", "requests", "urllib",
            "subprocess", "plan_series_state_write(",
            "connect_validated_bundle_to_dry_harness(",
            "run_dry_connection_harness(",
        ):
            self.assertNotIn(forbidden, source)

    def test_changed_persistence_contract_fails_closed(self):
        with mock.patch.object(evidence.persistence_contract,
                               "MAX_WRITES_PER_RUN", 5):
            facts = evidence.collect_filesystem_state_review_evidence()
        self.assertFalse(facts.trust_boundary_verified)
        self.assertEqual(
            review.review_filesystem_state_connection(facts).status,
            review.REVIEW_BLOCKED,
        )


if __name__ == "__main__":
    unittest.main()
