from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_runner_candidate as runner  # noqa: E402
import temporal_probe_series_state as series  # noqa: E402


BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"


def state(captured_at=BASE, values=("private-1",)):
    return series.create_temporal_probe_series_state(
        series_id=SERIES_ID,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort="rank",
        offset=1,
        hits=100,
        content_ids=values,
    )


class TemporalProbeSeriesRunnerCandidateTests(unittest.TestCase):
    def test_baseline_assessment_creates_plan_without_authorization(self):
        result = runner.run_temporal_series_candidate(
            state(), (), as_of=AS_OF, history_count=0
        )
        self.assertEqual(result.status, runner.RUNNER_PLAN_READY)
        self.assertTrue(result.success)
        self.assertEqual(
            result.assessment_status, "EXPLICIT_SERIES_BASELINE_PLANNED"
        )
        self.assertTrue(result.write_plan_created)
        self.assertFalse(result.filesystem_access_performed)
        self.assertFalse(result.active_runner_connected)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)

    def test_same_series_comparison_is_aggregate_only(self):
        previous = state(BASE, ("private-1", "private-2"))
        current = state(BASE + timedelta(days=1), ("private-2", "private-3"))
        result = runner.run_temporal_series_candidate(
            current,
            (series.serialize_temporal_probe_series_state(previous),),
            as_of=AS_OF,
            history_count=1,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.comparison_available)
        self.assertEqual(result.stability_classification, "OBSERVATION_ONLY")
        self.assertEqual(
            (result.retained_count, result.entered_count, result.exited_count),
            (1, 1, 1),
        )

    def test_blocked_assessment_never_reaches_store_plan(self):
        with mock.patch.object(
            runner.store, "plan_series_state_write"
        ) as plan:
            result = runner.run_temporal_series_candidate(
                state(), (), as_of=AS_OF, history_count=1
            )
        self.assertEqual(result.status, runner.RUNNER_BLOCKED)
        self.assertFalse(result.write_plan_created)
        plan.assert_not_called()

    def test_blocked_store_plan_fails_closed(self):
        blocked = runner.store.SeriesStateWritePlan(
            runner.store.STORE_CANDIDATE_VERSION,
            runner.store.WRITE_PLAN_BLOCKED,
            False, None, None, None, False, False, False,
            ("private detail",),
        )
        with mock.patch.object(
            runner.store, "plan_series_state_write", return_value=blocked
        ):
            result = runner.run_temporal_series_candidate(
                state(), (), as_of=AS_OF, history_count=0
            )
        self.assertEqual(result.reason_codes, ("SERIES_WRITE_PLAN_BLOCKED",))
        self.assertNotIn("private detail", json.dumps(result.to_dict()))

    def test_safe_output_contains_no_identifiers_or_write_metadata(self):
        result = runner.run_temporal_series_candidate(
            state(), (), as_of=AS_OF, history_count=0
        )
        encoded = json.dumps(result.to_dict())
        self.assertNotIn(SERIES_ID, encoded)
        self.assertNotIn("private-1", encoded)
        self.assertNotIn("filename", encoded)
        self.assertNotIn("sha256", encoded)

    def test_source_has_no_filesystem_external_or_active_runner_io(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "run_temporal_probe(", "write_temporal_probe_state(", "open(",
            "read_text(", "read_bytes(", "write_text(", "write_bytes(",
            "mkdir(", "unlink(", "os.", "urllib", "requests", "subprocess",
            "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
