from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_series_candidate_evidence as evidence  # noqa: E402


class TemporalSeriesCandidateEvidenceTests(unittest.TestCase):
    def test_isolated_chain_is_ready_but_not_connected_or_authorized(self):
        result = evidence.assess_temporal_series_candidate_evidence()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertTrue(result.implementation_evidence_candidate)
        self.assertEqual((result.checks_passed, result.checks_required), (8, 8))
        self.assertTrue(result.isolated_integration_adapter_verified)
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_dependency_regression_blocks_evidence(self):
        with mock.patch.object(
            evidence.orchestrator,
            "run_fixed_series_dry_orchestrator",
            side_effect=RuntimeError("secret path detail"),
        ):
            result = evidence.assess_temporal_series_candidate_evidence()
        encoded = json.dumps(result.to_dict())
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.implementation_evidence_candidate)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("path", encoded)

    def test_integration_adapter_regression_blocks_evidence(self):
        with mock.patch.object(
            evidence.integration,
            "run_series_integration_dry_run",
            side_effect=RuntimeError("private identifier detail"),
        ):
            result = evidence.assess_temporal_series_candidate_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.isolated_integration_adapter_verified)
        self.assertNotIn("private", json.dumps(result.to_dict()))

    def test_source_has_no_filesystem_or_external_io(self):
        source = Path(evidence.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "write_temporal_probe_state", "urllib", "requests",
            "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
