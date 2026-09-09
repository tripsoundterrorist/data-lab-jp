from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_dry_run as dry_run  # noqa: E402
import temporal_probe_series_state as series  # noqa: E402


BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_A = "series-20260909T000000Z-a1b2c3d4"
SERIES_B = "series-20260910T000000Z-b1c2d3e4"


def state(captured_at, values, series_id=SERIES_A):
    return series.create_temporal_probe_series_state(
        series_id=series_id,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort="rank",
        offset=1,
        hits=100,
        content_ids=values,
    )


class TemporalProbeSeriesDryRunTests(unittest.TestCase):
    def test_explicit_new_series_baseline_is_plan_only(self):
        result = dry_run.run_series_dry_run(
            state(BASE, ("cid-1",)), (), as_of=AS_OF, history_count=0
        )
        self.assertEqual(result.status, dry_run.BASELINE_PLANNED)
        self.assertTrue(result.success)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.baseline_activation_authorized)
        self.assertFalse(result.comparison_available)

    def test_same_series_valid_interval_is_assessed(self):
        previous = state(BASE, ("cid-1", "cid-2"))
        current = state(
            BASE + timedelta(days=1), ("cid-2", "cid-3")
        )
        result = dry_run.run_series_dry_run(
            current,
            (series.serialize_temporal_probe_series_state(previous),),
            as_of=AS_OF,
            history_count=1,
        )
        self.assertEqual(result.status, dry_run.COMPARISON_ASSESSED)
        self.assertEqual(result.stability_classification, "OBSERVATION_ONLY")
        self.assertEqual(
            (result.retained_count, result.entered_count, result.exited_count),
            (1, 1, 1),
        )
        self.assertFalse(result.state_write_authorized)

    def test_long_interval_is_blocked_by_existing_policy(self):
        previous = state(BASE, ("cid-1",))
        current = state(BASE + timedelta(days=3), ("cid-1",))
        result = dry_run.run_series_dry_run(
            current,
            (series.serialize_temporal_probe_series_state(previous),),
            as_of=AS_OF,
            history_count=1,
        )
        self.assertEqual(result.status, dry_run.BLOCKED)
        self.assertEqual(result.stability_classification, "ANOMALOUS_COMPARISON")
        self.assertFalse(result.api_request_authorized)

    def test_baseline_requires_zero_history(self):
        result = dry_run.run_series_dry_run(
            state(BASE, ("cid-1",)), (), as_of=AS_OF, history_count=1
        )
        self.assertEqual(result.status, dry_run.BLOCKED)
        self.assertIn("BASELINE_HISTORY_COUNT_MUST_BE_ZERO", result.reason_codes)

    def test_comparison_requires_positive_history(self):
        previous = state(BASE, ("cid-1",))
        current = state(BASE + timedelta(days=1), ("cid-1",))
        result = dry_run.run_series_dry_run(
            current,
            (series.serialize_temporal_probe_series_state(previous),),
            as_of=AS_OF,
            history_count=0,
        )
        self.assertEqual(result.status, dry_run.BLOCKED)

    def test_safe_output_contains_no_state_or_raw_identifier(self):
        raw = "cid-sensitive"
        result = dry_run.run_series_dry_run(
            state(BASE, (raw,)), (), as_of=AS_OF, history_count=0
        )
        encoded = json.dumps(result.to_dict())
        self.assertNotIn(raw, encoded)
        self.assertNotIn("series_id", encoded)
        self.assertNotIn("anonymous_item_ids", encoded)

    def test_source_has_no_filesystem_or_external_io(self):
        source = Path(dry_run.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "write_temporal_probe_state", "urllib", "requests",
            "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
