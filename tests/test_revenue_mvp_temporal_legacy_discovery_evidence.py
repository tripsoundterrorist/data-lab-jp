from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_legacy_discovery_evidence as evidence  # noqa: E402


class TemporalLegacyDiscoveryEvidenceTests(unittest.TestCase):
    def test_legacy_is_readable_but_never_comparable_or_migrated(self):
        result = evidence.assess_legacy_read_only_discovery()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertTrue(result.success)
        self.assertTrue(result.legacy_readable)
        self.assertFalse(result.legacy_comparison_allowed)
        self.assertTrue(result.same_series_selection_verified)
        self.assertTrue(result.legacy_exclusion_verified)
        self.assertTrue(result.cross_series_exclusion_verified)
        self.assertFalse(result.legacy_migration_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertEqual((result.checks_passed, result.checks_required), (7, 7))

    def test_discovery_regression_fails_closed_without_detail_leak(self):
        with mock.patch.object(
            evidence.discovery,
            "discover_latest_same_series",
            side_effect=RuntimeError("secret document detail"),
        ):
            result = evidence.assess_legacy_read_only_discovery()
        encoded = json.dumps(result.to_dict())
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.legacy_migration_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertNotIn("secret", encoded)

    def test_source_has_no_filesystem_external_or_write_io(self):
        source = Path(evidence.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "read_bytes(", "write_text(",
            "write_bytes(", "write_temporal_probe_state(", "mkdir(",
            "unlink(", "os.", "urllib", "requests", "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
