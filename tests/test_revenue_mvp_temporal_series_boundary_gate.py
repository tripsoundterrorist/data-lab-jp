from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_series_boundary_gate as gate  # noqa: E402


class TemporalSeriesBoundaryGateTests(unittest.TestCase):
    def test_current_contract_requires_schema_change(self):
        result = gate.assess_temporal_series_boundary()
        self.assertEqual(result.status, gate.SCHEMA_CHANGE_REQUIRED)
        self.assertFalse(result.current_schema_supports_series_boundary)
        self.assertFalse(result.current_runner_supports_series_boundary)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.history_reset_authorized)
        self.assertEqual(result.required_changes, gate.REQUIRED_CHANGES)

    def test_partial_implementation_fails_closed(self):
        with mock.patch.object(
            gate.temporal_probe_state,
            "STATE_FIELDS",
            gate.temporal_probe_state.STATE_FIELDS | {gate.SERIES_FIELD},
        ), mock.patch.object(
            gate.temporal_probe_state,
            "POPULATION_IDENTITY_FIELDS",
            gate.temporal_probe_state.POPULATION_IDENTITY_FIELDS
            + (gate.SERIES_FIELD,),
        ):
            result = gate.assess_temporal_series_boundary()
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertFalse(result.api_request_authorized)

    def test_internal_details_are_bounded(self):
        with mock.patch.object(
            gate.inspect,
            "signature",
            side_effect=RuntimeError("secret path detail"),
        ):
            result = gate.assess_temporal_series_boundary()
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("path", serialized)

    def test_source_has_no_state_or_external_mutation(self):
        source = Path(gate.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "write_temporal_probe_state", "urllib", "requests", "subprocess",
            "INSERT", "UPDATE", "DELETE", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
