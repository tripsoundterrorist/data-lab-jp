from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_discovery as discovery  # noqa: E402
import temporal_probe_series_state as series  # noqa: E402
import temporal_probe_state as legacy  # noqa: E402


BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_A = "series-20260909T000000Z-a1b2c3d4"
SERIES_B = "series-20260910T000000Z-b1c2d3e4"


def state(captured_at, series_id=SERIES_A, *, offset=1):
    return series.create_temporal_probe_series_state(
        series_id=series_id,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort="rank",
        offset=offset,
        hits=100,
        content_ids=("cid-1",),
    )


def encoded(value):
    return series.serialize_temporal_probe_series_state(value)


class TemporalProbeSeriesDiscoveryTests(unittest.TestCase):
    def test_latest_same_series_is_selected(self):
        current = state(BASE + timedelta(days=3))
        older = state(BASE)
        latest = state(BASE + timedelta(days=2))
        result = discovery.discover_latest_same_series(
            current, (encoded(latest), encoded(older)), as_of=AS_OF
        )
        self.assertEqual(result.status, discovery.LATEST_FOUND)
        self.assertTrue(result.comparison_candidate)
        self.assertEqual(result.selected, latest)

    def test_cross_series_is_excluded_not_compared(self):
        current = state(BASE + timedelta(days=3), SERIES_B)
        result = discovery.discover_latest_same_series(
            current, (encoded(state(BASE, SERIES_A)),), as_of=AS_OF
        )
        self.assertEqual(result.status, discovery.EXPLICIT_BASELINE_CANDIDATE)
        self.assertFalse(result.comparison_candidate)
        self.assertTrue(result.baseline_candidate)
        self.assertEqual(result.cross_series_excluded_count, 1)

    def test_legacy_is_read_only_and_excluded(self):
        current = state(BASE + timedelta(days=3))
        old = legacy.create_temporal_probe_state(
            captured_at=BASE,
            site="FANZA",
            service="digital",
            floor="videoa",
            source_sort="rank",
            offset=1,
            hits=100,
            content_ids=("cid-1",),
        )
        result = discovery.discover_latest_same_series(
            current,
            (legacy.serialize_temporal_probe_state(old),),
            as_of=AS_OF,
        )
        self.assertEqual(result.status, discovery.EXPLICIT_BASELINE_CANDIDATE)
        self.assertEqual(result.legacy_excluded_count, 1)

    def test_same_series_equal_or_future_timestamp_fails_closed(self):
        current = state(BASE + timedelta(days=2))
        result = discovery.discover_latest_same_series(
            current, (encoded(state(BASE + timedelta(days=2))),), as_of=AS_OF
        )
        self.assertEqual(result.status, discovery.FAIL_CLOSED)

    def test_duplicate_timestamp_is_ambiguous(self):
        current = state(BASE + timedelta(days=3))
        first = state(BASE)
        second = replace(
            first,
            legacy_state=replace(
                first.legacy_state,
                anonymous_item_ids=("prb_" + "a" * 32,),
            ),
        )
        result = discovery.discover_latest_same_series(
            current, (encoded(first), encoded(second)), as_of=AS_OF
        )
        self.assertEqual(result.status, discovery.FAIL_CLOSED)
        self.assertIn("AMBIGUOUS_SAME_SERIES_TIMESTAMP", result.reason_codes)

    def test_unreadable_document_fails_closed_without_echo(self):
        result = discovery.discover_latest_same_series(
            state(BASE + timedelta(days=3)),
            ({"secret": "https://invalid"},),
            as_of=AS_OF,
        )
        serialized = json.dumps(result.safe_dict())
        self.assertEqual(result.status, discovery.FAIL_CLOSED)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("https://", serialized)

    def test_other_population_is_ignored(self):
        current = state(BASE + timedelta(days=3))
        result = discovery.discover_latest_same_series(
            current, (encoded(state(BASE, offset=101)),), as_of=AS_OF
        )
        self.assertEqual(result.status, discovery.EXPLICIT_BASELINE_CANDIDATE)

    def test_source_has_no_filesystem_or_external_io(self):
        source = Path(discovery.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "write_", "urllib", "requests", "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
