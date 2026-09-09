from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_series_connection_readiness as readiness  # noqa: E402


class ConnectionReadinessTests(unittest.TestCase):
    def test_isolated_evidence_is_complete_but_connection_is_not_authorized(self):
        result = readiness.assess_connection_readiness()
        self.assertEqual(result.status, readiness.REVIEW_READY)
        self.assertTrue(result.evidence_complete)
        self.assertTrue(result.isolated_store_available)
        self.assertTrue(result.isolated_runner_available)
        self.assertTrue(result.legacy_read_only_verified)
        self.assertTrue(result.filename_identity_verified)
        self.assertTrue(result.four_population_harness_verified)
        self.assertEqual((result.checks_passed, result.checks_required), (10, 10))
        self.assertEqual(result.next_gate, readiness.NEXT_GATE)
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.connection_authorized)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_any_dependency_regression_fails_closed(self):
        with mock.patch.object(
            readiness.legacy_evidence,
            "assess_legacy_read_only_discovery",
            side_effect=RuntimeError("secret evidence detail"),
        ):
            result = readiness.assess_connection_readiness()
        encoded = json.dumps(result.to_dict())
        self.assertEqual(result.status, readiness.BLOCKED)
        self.assertIsNone(result.next_gate)
        self.assertFalse(result.connection_authorized)
        self.assertNotIn("secret", encoded)

    def test_source_has_no_active_filesystem_or_external_io(self):
        source = Path(readiness.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "run_temporal_probe(", "write_temporal_probe_state(", "open(",
            "read_text(", "read_bytes(", "write_text(", "write_bytes(",
            "mkdir(", "unlink(", "os.", "urllib", "requests", "subprocess",
            "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
