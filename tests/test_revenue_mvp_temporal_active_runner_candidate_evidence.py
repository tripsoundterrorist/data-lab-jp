from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_active_runner_candidate_evidence as evidence  # noqa: E402


class TemporalActiveRunnerCandidateEvidenceTests(unittest.TestCase):
    def test_current_candidate_passes_all_bounded_checks(self):
        result = evidence.assess_candidate_evidence()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertEqual((result.checks_passed, result.checks_required), (8, 8))
        self.assertTrue(result.implementation_evidence_candidate)
        self.assertTrue(result.test_filesystem_access_performed)
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_changed_design_fails_closed(self):
        changed = mock.Mock(
            status=evidence.design.BLOCKED,
            implementation_authorized=False,
            active_connection_authorized=False,
        )
        with mock.patch.object(evidence.design, "assess_design", return_value=changed):
            result = evidence.assess_candidate_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.implementation_evidence_candidate)
        self.assertFalse(result.active_pipeline_connected)

    def test_internal_error_is_safe(self):
        with mock.patch.object(evidence, "_bundle", side_effect=RuntimeError("private-value")):
            result = evidence.assess_candidate_evidence()
        rendered = json.dumps(result.to_dict())
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertNotIn("private-value", rendered)


if __name__ == "__main__":
    unittest.main()
