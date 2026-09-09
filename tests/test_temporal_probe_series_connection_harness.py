from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_connection_harness as harness  # noqa: E402
import temporal_probe_series_state as series  # noqa: E402

BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"


def state(identity, captured_at=BASE):
    return series.create_temporal_probe_series_state(
        series_id=SERIES_ID, captured_at=captured_at, site="FANZA",
        service="digital", floor="videoa", source_sort=identity[0],
        offset=identity[1], hits=identity[2], content_ids=("private-1",),
    )


def states(captured_at=BASE):
    return tuple(state(identity, captured_at) for identity in harness.FIXED_POPULATIONS)


def documents(value=()):
    return {identity: value for identity in harness.FIXED_POPULATIONS}


def histories(value=0):
    return {identity: value for identity in harness.FIXED_POPULATIONS}


class TemporalProbeSeriesConnectionHarnessTests(unittest.TestCase):
    def test_four_baseline_plans_complete_without_connection(self):
        result = harness.run_dry_connection_harness(
            current_states=states(), documents_by_population=documents(),
            history_counts=histories(), as_of=AS_OF,
        )
        self.assertEqual(result.status, harness.HARNESS_COMPLETE)
        self.assertEqual((result.succeeded_count, result.skipped_count), (4, 0))
        self.assertTrue(all(item.write_plan_created for item in result.populations))
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.filesystem_access_performed)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_four_same_series_comparisons_complete(self):
        previous = {
            identity: (series.serialize_temporal_probe_series_state(
                state(identity, BASE)
            ),)
            for identity in harness.FIXED_POPULATIONS
        }
        result = harness.run_dry_connection_harness(
            current_states=states(BASE + timedelta(days=1)),
            documents_by_population=previous,
            history_counts=histories(1),
            as_of=AS_OF,
        )
        self.assertTrue(result.success)
        self.assertTrue(all(
            item.comparison_available for item in result.populations
        ))

    def test_wrong_order_fails_before_runner(self):
        values = list(states())
        values[0], values[1] = values[1], values[0]
        with mock.patch.object(
            harness.runner, "run_temporal_series_candidate"
        ) as run:
            result = harness.run_dry_connection_harness(
                current_states=values, documents_by_population=documents(),
                history_counts=histories(), as_of=AS_OF,
            )
        self.assertEqual(result.evaluated_count, 0)
        run.assert_not_called()

    def test_first_failure_stops_remaining_populations(self):
        counts = histories()
        counts[harness.FIXED_POPULATIONS[0]] = 1
        result = harness.run_dry_connection_harness(
            current_states=states(), documents_by_population=documents(),
            history_counts=counts, as_of=AS_OF,
        )
        self.assertEqual((result.failed_count, result.skipped_count), (1, 3))
        self.assertEqual(
            tuple(item.status for item in result.populations[1:]),
            ("NOT_RUN", "NOT_RUN", "NOT_RUN"),
        )

    def test_missing_mapping_key_fails_closed(self):
        docs = documents()
        del docs[harness.FIXED_POPULATIONS[-1]]
        result = harness.run_dry_connection_harness(
            current_states=states(), documents_by_population=docs,
            history_counts=histories(), as_of=AS_OF,
        )
        self.assertEqual(result.status, harness.HARNESS_BLOCKED)
        self.assertEqual(result.evaluated_count, 0)

    def test_safe_output_contains_no_identifiers(self):
        result = harness.run_dry_connection_harness(
            current_states=states(), documents_by_population=documents(),
            history_counts=histories(), as_of=AS_OF,
        )
        encoded = json.dumps(result.to_dict())
        self.assertNotIn(SERIES_ID, encoded)
        self.assertNotIn("private-1", encoded)

    def test_source_has_no_active_filesystem_or_external_io(self):
        source = Path(harness.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "run_temporal_probe(", "write_temporal_probe_state(", "open(",
            "read_text(", "read_bytes(", "write_text(", "write_bytes(",
            "mkdir(", "unlink(", "os.", "urllib", "requests", "subprocess",
            "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
