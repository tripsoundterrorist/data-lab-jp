from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_state as series  # noqa: E402
import temporal_probe_state as legacy  # noqa: E402


PREVIOUS = datetime(2026, 9, 9, tzinfo=timezone.utc)
CURRENT = PREVIOUS + timedelta(days=1)
AS_OF = CURRENT + timedelta(hours=1)
SERIES_A = "series-20260909T000000Z-a1b2c3d4"
SERIES_B = "series-20260910T000000Z-b1c2d3e4"


def state(series_id=SERIES_A, captured_at=PREVIOUS, values=("cid-1",)):
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


class TemporalProbeSeriesStateTests(unittest.TestCase):
    def test_explicit_series_is_required(self):
        with self.assertRaises(ValueError):
            state(series_id="")

    def test_series_identity_is_part_of_population_identity(self):
        self.assertEqual(state().population_identity[-1], SERIES_A)
        self.assertIn("series_id", series.POPULATION_IDENTITY_FIELDS)

    def test_same_series_comparison_uses_existing_math(self):
        result = series.compare_temporal_probe_series_states(
            state(values=("cid-1", "cid-2")),
            state(captured_at=CURRENT, values=("cid-2", "cid-3")),
            as_of=AS_OF,
        )
        self.assertTrue(result.comparison_valid)
        self.assertEqual(
            (result.retained_count, result.entered_count, result.exited_count),
            (1, 1, 1),
        )

    def test_cross_series_comparison_is_rejected(self):
        result = series.compare_temporal_probe_series_states(
            state(), state(series_id=SERIES_B, captured_at=CURRENT), as_of=AS_OF
        )
        self.assertFalse(result.comparison_valid)
        self.assertEqual(result.reason_codes, ("CROSS_SERIES_COMPARISON",))

    def test_v02_round_trip_has_exact_fields_and_no_raw_id(self):
        raw = "cid-sensitive"
        encoded = series.serialize_temporal_probe_series_state(
            state(values=(raw,))
        )
        self.assertNotIn(raw, encoded)
        document = json.loads(encoded)
        self.assertEqual(set(document), series.STATE_FIELDS)
        self.assertEqual(
            series.deserialize_temporal_probe_series_state(encoded),
            state(values=(raw,)),
        )

    def test_legacy_state_is_readable_but_not_comparable(self):
        old = legacy.create_temporal_probe_state(
            captured_at=PREVIOUS,
            site="FANZA",
            service="digital",
            floor="videoa",
            source_sort="rank",
            offset=1,
            hits=100,
            content_ids=("cid-1",),
        )
        result = series.classify_temporal_state_document(
            legacy.serialize_temporal_probe_state(old)
        )
        self.assertEqual(result.status, series.LEGACY_READ_ONLY)
        self.assertTrue(result.readable)
        self.assertFalse(result.comparison_allowed)

    def test_invalid_series_fails_validation(self):
        result = series.validate_temporal_probe_series_state(
            replace(state(), series_id="../series")
        )
        self.assertFalse(result.valid)
        self.assertIn("INVALID_SERIES_ID", result.reason_codes)

    def test_source_has_no_filesystem_or_external_io(self):
        source = Path(series.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "write_", "urllib", "requests", "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
