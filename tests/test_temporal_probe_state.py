from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from temporal_probe_state import (  # noqa: E402
    STATE_SCHEMA_VERSION,
    anonymous_probe_item_id,
    compare_temporal_probe_states,
    create_temporal_probe_state,
    deserialize_temporal_probe_state,
    serialize_temporal_probe_state,
    validate_temporal_probe_state,
)


PREVIOUS_AT = datetime(2026, 8, 24, 1, 0, tzinfo=timezone.utc)
CURRENT_AT = PREVIOUS_AT + timedelta(days=1)
AS_OF = CURRENT_AT + timedelta(hours=1)


def ids(start: int, count: int) -> list[str]:
    return [f"cid-{number:04d}" for number in range(start, start + count)]


def state(values: list[str], *, captured_at: datetime = PREVIOUS_AT, **updates: object):
    arguments = {
        "captured_at": captured_at,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "source_sort": "rank",
        "offset": 1,
        "hits": 100,
        "content_ids": values,
    }
    arguments.update(updates)
    return create_temporal_probe_state(**arguments)


class TemporalProbeStateTests(unittest.TestCase):
    def test_a_all_items_retained(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 100)), state(ids(0, 100), captured_at=CURRENT_AT), as_of=AS_OF
        )
        self.assertTrue(result.comparison_valid)
        self.assertEqual((result.retained_count, result.entered_count, result.exited_count), (100, 0, 0))
        self.assertEqual((result.retention_rate, result.jaccard), (1.0, 1.0))

    def test_b_half_turnover(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 100)), state(ids(50, 100), captured_at=CURRENT_AT), as_of=AS_OF
        )
        self.assertEqual((result.retained_count, result.entered_count, result.exited_count), (50, 50, 50))

    def test_c_complete_turnover(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 100)), state(ids(100, 100), captured_at=CURRENT_AT), as_of=AS_OF
        )
        self.assertEqual(result.retained_count, 0)
        self.assertEqual((result.turnover_rate, result.jaccard), (1.0, 0.0))

    def test_d_population_identity_mismatch_is_rejected(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 1)), state(ids(0, 1), captured_at=CURRENT_AT, floor="videoc"), as_of=AS_OF
        )
        self.assertFalse(result.comparison_valid)
        self.assertEqual(result.reason_codes, ("POPULATION_IDENTITY_MISMATCH",))

    def test_e_sort_mismatch_is_rejected(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 1)), state(ids(0, 1), captured_at=CURRENT_AT, source_sort="review"), as_of=AS_OF
        )
        self.assertFalse(result.comparison_valid)

    def test_f_offset_mismatch_is_rejected(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 1)), state(ids(0, 1), captured_at=CURRENT_AT, offset=101), as_of=AS_OF
        )
        self.assertFalse(result.comparison_valid)

    def test_g_hits_mismatch_is_rejected(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 1)), state(ids(0, 1), captured_at=CURRENT_AT, hits=50), as_of=AS_OF
        )
        self.assertFalse(result.comparison_valid)

    def test_h_duplicate_anonymous_id_is_invalid(self) -> None:
        value = state(ids(0, 2))
        invalid = replace(value, anonymous_item_ids=(value.anonymous_item_ids[0],) * 2)
        self.assertFalse(validate_temporal_probe_state(invalid).valid)

    def test_i_count_mismatch_is_invalid(self) -> None:
        self.assertFalse(validate_temporal_probe_state(replace(state(ids(0, 2)), returned_count=1)).valid)

    def test_j_malformed_anonymous_id_is_invalid(self) -> None:
        value = replace(state(ids(0, 1)), anonymous_item_ids=("cid-raw",))
        self.assertFalse(validate_temporal_probe_state(value).valid)

    def test_k_timestamp_reversal_is_rejected(self) -> None:
        result = compare_temporal_probe_states(
            state(ids(0, 1)), state(ids(0, 1), captured_at=PREVIOUS_AT), as_of=AS_OF
        )
        self.assertFalse(result.comparison_valid)
        self.assertEqual(result.reason_codes, ("NON_INCREASING_TIMESTAMP",))

    def test_l_unknown_schema_is_invalid(self) -> None:
        value = replace(state(ids(0, 1)), state_schema_version="9.9")
        self.assertFalse(validate_temporal_probe_state(value).valid)

    def test_m_forbidden_or_path_field_is_rejected(self) -> None:
        document = state(ids(0, 1)).to_dict()
        for field, value in (
            ("content_id", "raw"),
            ("affiliateURL", "https://example.invalid"),
            ("path", "../../state.json"),
        ):
            with self.subTest(field=field):
                candidate = dict(document)
                candidate[field] = value
                self.assertIsNone(deserialize_temporal_probe_state(candidate))

    def test_n_anonymous_id_is_deterministic(self) -> None:
        first = state(["cid-0001"]).anonymous_item_ids[0]
        second = state(["cid-0001"]).anonymous_item_ids[0]
        self.assertEqual(first, second)

    def test_o_different_content_ids_normally_differ(self) -> None:
        first = state(["cid-0001"]).anonymous_item_ids[0]
        second = state(["cid-0002"]).anonymous_item_ids[0]
        self.assertNotEqual(first, second)

    def test_p_serialized_state_contains_no_raw_content_id(self) -> None:
        raw = "cid-sensitive-fixture"
        serialized = serialize_temporal_probe_state(state([raw]))
        document = json.loads(serialized)
        self.assertNotIn(raw, serialized)
        self.assertEqual(set(document), {
            "state_schema_version", "captured_at", "site", "service", "floor",
            "source_sort", "offset", "hits", "returned_count", "anonymous_item_ids",
        })
        self.assertEqual(deserialize_temporal_probe_state(serialized).state_schema_version, STATE_SCHEMA_VERSION)

    def test_q_internal_exception_fails_closed(self) -> None:
        with mock.patch("temporal_probe_state._compare_validated", side_effect=RuntimeError):
            result = compare_temporal_probe_states(
                state(ids(0, 1)), state(ids(0, 1), captured_at=CURRENT_AT), as_of=AS_OF
            )
        self.assertFalse(result.comparison_valid)
        self.assertEqual(result.reason_codes, ("INTERNAL_COMPARISON_ERROR",))


if __name__ == "__main__":
    unittest.main()
