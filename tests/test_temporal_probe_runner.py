from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from temporal_probe_runner import run_temporal_probe  # noqa: E402
from temporal_probe_state import create_temporal_probe_state  # noqa: E402
from temporal_probe_state_store import (  # noqa: E402
    DEFAULT_STATE_DIRECTORY,
    StoreResult,
    write_temporal_probe_state,
)


FIRST_AT = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
SECOND_AT = FIRST_AT + timedelta(days=1)
AS_OF = SECOND_AT + timedelta(hours=1)


def content_ids(start: int, count: int) -> list[str]:
    return [f"cid-{number:04d}" for number in range(start, start + count)]


def fixture(values: list[str], *, captured_at: datetime = FIRST_AT, source_sort: str = "rank", offset: int = 1, hits: int = 100):
    return {
        "captured_at": captured_at,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "source_sort": source_sort,
        "offset": offset,
        "hits": hits,
        "result_count": len(values),
        "items": [{"content_id": value} for value in values],
    }


def stored_state(values: list[str], *, captured_at: datetime = FIRST_AT, source_sort: str = "rank", offset: int = 1, hits: int = 100):
    return create_temporal_probe_state(
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        content_ids=values,
    )


class TemporalProbeRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        DEFAULT_STATE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            DEFAULT_STATE_DIRECTORY.rmdir()
            DEFAULT_STATE_DIRECTORY.parent.rmdir()
        except OSError:
            pass

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="runner-", dir=DEFAULT_STATE_DIRECTORY)
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def execute(self, value: object, *, dry_run: bool = False):
        return run_temporal_probe(
            value,
            as_of=AS_OF,
            dry_run=dry_run,
            output_directory=self.directory,
        )

    def test_a_first_rank_creates_baseline(self) -> None:
        result = self.execute(fixture(content_ids(0, 100)))
        self.assertTrue(result.success and result.state_saved)
        self.assertFalse(result.comparison_available)
        self.assertEqual(result.reason_codes, ("BASELINE_CREATED",))

    def test_b_second_identical_rank_is_fully_retained(self) -> None:
        write_temporal_probe_state(stored_state(content_ids(0, 100)), output_directory=self.directory)
        result = self.execute(fixture(content_ids(0, 100), captured_at=SECOND_AT))
        self.assertTrue(result.comparison_available)
        self.assertEqual((result.retained_count, result.retention_rate), (100, 1.0))

    def test_c_second_rank_half_changes(self) -> None:
        write_temporal_probe_state(stored_state(content_ids(0, 100)), output_directory=self.directory)
        result = self.execute(fixture(content_ids(50, 100), captured_at=SECOND_AT))
        self.assertEqual((result.retained_count, result.entered_count, result.exited_count), (50, 50, 50))

    def test_d_review_population_works(self) -> None:
        result = self.execute(fixture(content_ids(0, 100), source_sort="review"))
        self.assertTrue(result.success)
        self.assertEqual(result.observation_semantics, "review-sorted population turnover")

    def test_e_rank_previous_is_not_used_for_review(self) -> None:
        write_temporal_probe_state(stored_state(content_ids(0, 10)), output_directory=self.directory)
        result = self.execute(fixture(content_ids(0, 10), captured_at=SECOND_AT, source_sort="review"))
        self.assertTrue(result.success)
        self.assertFalse(result.comparison_available)

    def test_f_offset_difference_is_not_compared(self) -> None:
        write_temporal_probe_state(stored_state(content_ids(0, 10)), output_directory=self.directory)
        result = self.execute(fixture(content_ids(0, 10), captured_at=SECOND_AT, offset=101))
        self.assertFalse(result.comparison_available)

    def test_g_hits_difference_is_not_compared(self) -> None:
        write_temporal_probe_state(stored_state(content_ids(0, 10)), output_directory=self.directory)
        result = self.execute(fixture(content_ids(0, 10), captured_at=SECOND_AT, hits=50))
        self.assertFalse(result.comparison_available)

    def test_h_duplicate_content_id_fails_closed(self) -> None:
        result = self.execute(fixture(["cid-1", "cid-1"]))
        self.assertFalse(result.success)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_i_result_count_mismatch_fails_closed(self) -> None:
        value = fixture(["cid-1"])
        value["result_count"] = 2
        self.assertFalse(self.execute(value).success)

    def test_j_missing_content_id_fails_closed(self) -> None:
        value = fixture(["cid-1"])
        value["items"] = [{}]
        self.assertFalse(self.execute(value).success)

    def test_k_malformed_content_id_fails_closed(self) -> None:
        self.assertFalse(self.execute(fixture(["../../raw"])).success)

    def test_l_future_timestamp_fails_closed(self) -> None:
        self.assertFalse(self.execute(fixture(["cid-1"], captured_at=AS_OF + timedelta(seconds=1))).success)

    def test_m_store_conflict_is_failure(self) -> None:
        with mock.patch(
            "temporal_probe_runner.state_store.write_temporal_probe_state",
            return_value=StoreResult(False, False, True, ("STATE_CONFLICT",)),
        ):
            result = self.execute(fixture(["cid-1"]))
        self.assertFalse(result.success)
        self.assertFalse(result.state_saved)

    def test_n_store_path_error_is_failure(self) -> None:
        result = run_temporal_probe(
            fixture(["cid-1"]),
            as_of=AS_OF,
            output_directory=ROOT / "scripts",
        )
        self.assertFalse(result.success)

    def test_o_baseline_does_not_fabricate_comparison_metrics(self) -> None:
        result = self.execute(fixture(["cid-1"]))
        self.assertIsNone(result.retained_count)
        self.assertIsNone(result.jaccard)

    def test_p_result_contains_no_raw_content_id(self) -> None:
        raw = "cid-sensitive-fixture"
        result = self.execute(fixture([raw]))
        self.assertNotIn(raw, repr(result.to_dict()))

    def test_q_result_contains_no_anonymous_id_collection(self) -> None:
        result = self.execute(fixture(["cid-1"]))
        self.assertNotIn("anonymous_item_ids", result.to_dict())
        self.assertFalse(any(isinstance(value, (list, set, tuple)) for key, value in result.to_dict().items() if key != "reason_codes"))

    def test_r_dry_run_changes_no_filesystem_state(self) -> None:
        before = set(self.directory.iterdir())
        result = self.execute(fixture(["cid-1"]), dry_run=True)
        self.assertTrue(result.success)
        self.assertFalse(result.state_saved)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_s_unknown_sort_fails_closed(self) -> None:
        self.assertFalse(self.execute(fixture(["cid-1"], source_sort="date")).success)

    def test_t_internal_exception_fails_closed(self) -> None:
        with mock.patch("temporal_probe_runner._state_from_probe_result", side_effect=RuntimeError):
            result = self.execute(fixture(["cid-1"]))
        self.assertFalse(result.success)
        self.assertEqual(result.reason_codes, ("INTERNAL_RUNNER_ERROR",))


if __name__ == "__main__":
    unittest.main()
