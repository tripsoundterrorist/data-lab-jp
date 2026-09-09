from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_probe_series_state as series  # noqa: E402
import temporal_probe_series_state_store_candidate as store  # noqa: E402


CAPTURED = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = CAPTURED + timedelta(days=1)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"


def state(*, series_id=SERIES_ID, captured_at=CAPTURED):
    return series.create_temporal_probe_series_state(
        series_id=series_id,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort="rank",
        offset=1,
        hits=100,
        content_ids=("private-item-1", "private-item-2"),
    )


class TemporalProbeSeriesStateStoreCandidateTests(unittest.TestCase):
    def test_valid_state_produces_memory_only_series_aware_plan(self):
        result = store.plan_series_state_write(state(), as_of=AS_OF)
        self.assertEqual(result.status, store.WRITE_PLAN_READY)
        self.assertTrue(result.success)
        self.assertTrue(result.series_aware_identity)
        self.assertFalse(result.filesystem_access_performed)
        self.assertFalse(result.state_write_authorized)
        self.assertRegex(result.filename, store.STATE_FILENAME)
        self.assertRegex(result.document_sha256, re.compile(r"[a-f0-9]{64}\Z"))
        self.assertGreater(result.document_bytes, 0)

    def test_same_series_is_stable_and_another_series_is_distinct(self):
        first = store.plan_series_state_write(state(), as_of=AS_OF)
        same = store.plan_series_state_write(state(), as_of=AS_OF)
        other = store.plan_series_state_write(
            state(series_id="series-20260910T000000Z-b1c2d3e4"),
            as_of=AS_OF,
        )
        self.assertEqual(first.filename, same.filename)
        self.assertNotEqual(first.filename, other.filename)

    def test_raw_identifiers_are_not_returned(self):
        encoded = json.dumps(
            store.plan_series_state_write(state(), as_of=AS_OF).to_dict()
        )
        self.assertNotIn(SERIES_ID, encoded)
        self.assertNotIn("private-item", encoded)

    def test_future_or_malformed_state_fails_closed(self):
        future = state(captured_at=AS_OF + timedelta(seconds=1))
        for value in (future, object(), None):
            with self.subTest(value=type(value).__name__):
                result = store.plan_series_state_write(value, as_of=AS_OF)
                self.assertEqual(result.status, store.WRITE_PLAN_BLOCKED)
                self.assertFalse(result.state_write_authorized)
                self.assertIsNone(result.filename)

    def test_oversized_serialization_fails_closed(self):
        with mock.patch.object(
            store.series_state,
            "serialize_temporal_probe_series_state",
            return_value="x" * (store.MAX_STATE_BYTES + 1),
        ):
            result = store.plan_series_state_write(state(), as_of=AS_OF)
        self.assertEqual(result.reason_codes, ("SERIES_STATE_TOO_LARGE",))

    def test_source_has_no_filesystem_or_external_io(self):
        source = Path(store.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "read_bytes(", "write_text(",
            "write_bytes(", "mkdir(", "unlink(", "replace(", "os.",
            "urllib", "requests", "subprocess", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
