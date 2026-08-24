from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from temporal_probe_adapter import (  # noqa: E402
    ProbeRequest,
    adapt_response,
    build_request_plan,
    execute_plan,
)
from temporal_probe_runner import RunnerResult  # noqa: E402


CAPTURED = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)
AS_OF = CAPTURED + timedelta(minutes=1)


def request(source_sort: str = "rank", offset: int = 1, hits: int = 100) -> ProbeRequest:
    return ProbeRequest("FANZA", "digital", "videoa", source_sort, offset, hits)


def response(expected: ProbeRequest, values: list[str] | None = None) -> dict[str, object]:
    identifiers = values if values is not None else ["cid-001", "cid-002"]
    return {
        "request": expected.to_dict(),
        "success": True,
        "result_count": len(identifiers),
        "total_count": 50000,
        "elapsed_ms": 25,
        "items": [
            {
                "content_id": value,
                "review_average_present": index % 2 == 0,
                "review_count_present": True,
                "metadata_present": True,
            }
            for index, value in enumerate(identifiers)
        ],
        "error_classification": None,
    }


def runner_result(*, success: bool = True, saved: bool = True) -> RunnerResult:
    return RunnerResult(
        success, "rank", 1, 100, "2026-08-24T08:00:00Z",
        "rank-sorted population turnover", saved, False, None, None,
        2, None, None, None, None, None, None, None, None,
        ("BASELINE_CREATED",) if success else ("STATE_CONFLICT",),
    )


class TemporalProbeAdapterTests(unittest.TestCase):
    def run_one(self, expected: ProbeRequest, value: object, runner=mock.DEFAULT):
        chosen = mock.Mock(return_value=runner_result()) if runner is mock.DEFAULT else runner
        return adapt_response(
            value, expected, captured_at=CAPTURED, as_of=AS_OF, runner=chosen,
            output_directory=ROOT / "logs" / "probes" / "state",
        ), chosen

    def test_a_rank_offset_1_safe_aggregate_and_runner_input(self) -> None:
        result, runner = self.run_one(request(), response(request()))
        self.assertTrue(result.success)
        self.assertEqual((result.review_average_coverage, result.metadata_coverage), (1, 2))
        self.assertEqual(runner.call_args.args[0]["items"], [{"content_id": "cid-001"}, {"content_id": "cid-002"}])

    def test_b_rank_offset_101_succeeds(self) -> None:
        expected = request(offset=101)
        self.assertTrue(self.run_one(expected, response(expected))[0].success)

    def test_c_review_offset_1_succeeds(self) -> None:
        expected = request("review", 1)
        self.assertTrue(self.run_one(expected, response(expected))[0].success)

    def test_d_review_offset_101_succeeds(self) -> None:
        expected = request("review", 101)
        self.assertTrue(self.run_one(expected, response(expected))[0].success)

    def test_e_content_id_only_crosses_runner_boundary(self) -> None:
        raw = "sensitive-content-id"
        result, runner = self.run_one(request(), response(request(), [raw]))
        self.assertIn(raw, repr(runner.call_args.args[0]))
        self.assertNotIn(raw, repr(result))

    def test_f_anonymous_ids_are_not_in_result(self) -> None:
        result, _ = self.run_one(request(), response(request()))
        self.assertNotIn("anonymous_item_ids", repr(result))

    def test_g_duplicate_content_id_fails_closed(self) -> None:
        result, runner = self.run_one(request(), response(request(), ["same", "same"]))
        self.assertFalse(result.success)
        runner.assert_not_called()

    def test_h_result_count_mismatch_fails_closed(self) -> None:
        value = response(request())
        value["result_count"] = 1
        self.assertFalse(self.run_one(request(), value)[0].success)

    def test_i_request_identity_mismatch_fails_closed(self) -> None:
        value = response(request())
        value["request"] = request(offset=101).to_dict()
        self.assertEqual(self.run_one(request(), value)[0].reason_codes, ("REQUEST_IDENTITY_MISMATCH",))

    def test_j_unknown_sort_is_rejected(self) -> None:
        expected = request("date")
        self.assertEqual(self.run_one(expected, response(expected))[0].reason_codes, ("REQUEST_NOT_ALLOWED",))

    def test_k_unlisted_offset_is_rejected(self) -> None:
        expected = request(offset=2)
        self.assertFalse(self.run_one(expected, response(expected))[0].success)

    def test_l_hits_other_than_100_is_rejected(self) -> None:
        expected = request(hits=50)
        self.assertFalse(self.run_one(expected, response(expected))[0].success)

    def test_m_rate_limit_stops_remaining(self) -> None:
        calls = 0
        def fetch(expected):
            nonlocal calls
            calls += 1
            value = response(expected)
            value.update(success=False, result_count=None, total_count=None, items=[], error_classification="RATE_LIMIT")
            return value
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, fetch_response=fetch, runner=mock.Mock(), delay=mock.Mock())
        self.assertEqual((calls, result.attempted_request_count), (1, 1))

    def test_n_api_error_stops_remaining(self) -> None:
        fetch = mock.Mock(side_effect=lambda expected: {**response(expected), "success": False, "result_count": None, "total_count": None, "items": [], "error_classification": "API_ERROR"})
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, fetch_response=fetch, runner=mock.Mock(), delay=mock.Mock())
        self.assertTrue(result.stopped_early)
        self.assertEqual(fetch.call_count, 1)

    def test_o_malformed_response_stops_remaining(self) -> None:
        fetch = mock.Mock(return_value={"raw": "forbidden"})
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, fetch_response=fetch, runner=mock.Mock(), delay=mock.Mock())
        self.assertEqual((fetch.call_count, result.reason_codes), (1, ("MALFORMED_RESPONSE",)))

    def test_p_runner_failure_stops_remaining(self) -> None:
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, fetch_response=lambda expected: response(expected), runner=mock.Mock(return_value=runner_result(success=False, saved=False)), delay=mock.Mock())
        self.assertEqual((result.completed_request_count, result.attempted_request_count), (0, 1))

    def test_q_store_failure_via_runner_stops_remaining(self) -> None:
        failed = mock.Mock(return_value=runner_result(success=False, saved=False))
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, fetch_response=lambda expected: response(expected), runner=failed, delay=mock.Mock())
        self.assertTrue(result.stopped_early)
        self.assertEqual(failed.call_count, 1)

    def test_r_partial_success_is_preserved_without_rollback(self) -> None:
        runner = mock.Mock(side_effect=[runner_result(), runner_result(success=False, saved=False)])
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, fetch_response=lambda expected: response(expected), runner=runner, delay=mock.Mock())
        self.assertEqual((result.completed_request_count, result.attempted_request_count), (1, 2))
        self.assertEqual(result.partial_success_policy, "PRESERVE_COMPLETED_STATES_STOP_REMAINING")

    def test_s_dry_run_builds_plan_without_dependencies_or_files(self) -> None:
        result = execute_plan(captured_at=CAPTURED, as_of=AS_OF, dry_run=True)
        plan = build_request_plan(1.5)
        self.assertEqual((result.attempted_request_count, len(plan.requests)), (0, 4))
        self.assertEqual([(item.source_sort, item.offset, item.hits) for item in plan.requests], [("rank", 1, 100), ("rank", 101, 100), ("review", 1, 100), ("review", 101, 100)])

    def test_t_internal_exception_fails_closed(self) -> None:
        with mock.patch("temporal_probe_adapter._validate_identity", side_effect=RuntimeError):
            result, _ = self.run_one(request(), response(request()))
        self.assertEqual(result.reason_codes, ("INTERNAL_ADAPTER_ERROR",))


if __name__ == "__main__":
    unittest.main()
