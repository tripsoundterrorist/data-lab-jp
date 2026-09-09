from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_series_connection_review as review  # noqa: E402


class TemporalSeriesConnectionReviewTests(unittest.TestCase):
    def test_direct_connection_is_blocked_with_bounded_next_steps(self):
        result = review.assess_temporal_series_connection()
        self.assertEqual(result.status, review.CONNECTION_DESIGN_REQUIRED)
        self.assertTrue(result.isolated_integration_available)
        self.assertFalse(result.active_schema_series_aware)
        self.assertFalse(result.active_runner_series_aware)
        self.assertFalse(result.active_store_series_aware)
        self.assertTrue(result.active_adapter_write_path_present)
        self.assertFalse(result.connection_authorized)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.history_migration_authorized)
        self.assertEqual(result.required_isolated_steps, review.REQUIRED_ISOLATED_STEPS)

    def test_partial_active_change_fails_closed(self):
        with mock.patch.object(
            review.active_state,
            "STATE_FIELDS",
            review.active_state.STATE_FIELDS | {"series_id"},
        ), mock.patch.object(
            review.active_state,
            "POPULATION_IDENTITY_FIELDS",
            review.active_state.POPULATION_IDENTITY_FIELDS + ("series_id",),
        ):
            result = review.assess_temporal_series_connection()
        self.assertEqual(result.status, review.FAIL_CLOSED)
        self.assertFalse(result.connection_authorized)

    def test_introspection_failure_does_not_leak_details(self):
        with mock.patch.object(
            review.inspect,
            "getsource",
            side_effect=RuntimeError("secret source path"),
        ):
            result = review.assess_temporal_series_connection()
        encoded = json.dumps(result.to_dict())
        self.assertEqual(result.status, review.FAIL_CLOSED)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("source path", encoded)

    def test_source_has_no_execution_or_mutation(self):
        source = Path(review.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "run_series_integration_dry_run(", "run_temporal_probe(",
            "write_temporal_probe_state(", "urllib", "requests", "subprocess",
            "INSERT", "UPDATE", "DELETE", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
