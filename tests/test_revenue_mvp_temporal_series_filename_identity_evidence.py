from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_series_filename_identity_evidence as evidence  # noqa: E402


class FilenameIdentityEvidenceTests(unittest.TestCase):
    def test_all_filename_and_identity_boundaries_are_verified(self):
        result = evidence.assess_filename_identity()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertTrue(result.success)
        self.assertTrue(result.deterministic_plan_verified)
        self.assertTrue(result.series_filename_boundary_verified)
        self.assertTrue(result.population_filename_boundary_verified)
        self.assertTrue(result.timestamp_filename_boundary_verified)
        self.assertTrue(result.same_identity_conflict_signal_verified)
        self.assertTrue(result.comparison_identity_includes_series)
        self.assertFalse(result.raw_series_id_exposed)
        self.assertFalse(result.filesystem_access_performed)
        self.assertFalse(result.state_write_authorized)
        self.assertEqual((result.checks_passed, result.checks_required), (8, 8))

    def test_store_regression_fails_closed_without_detail_leak(self):
        with mock.patch.object(
            evidence.store, "plan_series_state_write",
            side_effect=RuntimeError("secret filename detail"),
        ):
            result = evidence.assess_filename_identity()
        encoded = json.dumps(result.to_dict())
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.state_write_authorized)
        self.assertNotIn("secret", encoded)

    def test_source_has_no_filesystem_external_or_write_io(self):
        source = Path(evidence.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "read_bytes(",
            "write_temporal_probe_state(", "mkdir(", "unlink(", "os.",
            "urllib", "requests", "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
