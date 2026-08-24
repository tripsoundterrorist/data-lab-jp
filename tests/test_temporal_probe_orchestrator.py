from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_probe_orchestrator as orchestrator  # noqa: E402
from temporal_probe_adapter import ProbeRequest, RequestPlan  # noqa: E402
from temporal_probe_runner import RunnerResult  # noqa: E402
from temporal_probe_state import create_temporal_probe_state  # noqa: E402
from temporal_probe_state_store import (  # noqa: E402
    DEFAULT_STATE_DIRECTORY,
    write_temporal_probe_state,
)


FIRST = datetime(2026, 8, 25, 5, 0, tzinfo=timezone.utc)
SECOND = FIRST + timedelta(days=1)
AS_OF = SECOND + timedelta(hours=1)


def ids(start: int = 0, count: int = 2) -> list[str]:
    return [f"fixture-{number:04d}" for number in range(start, start + count)]


def response(request: ProbeRequest, values: list[str] | None = None):
    selected = values if values is not None else ids()
    return {
        "request": request.to_dict(),
        "success": True,
        "result_count": len(selected),
        "total_count": 50000,
        "elapsed_ms": 25,
        "items": [
            {
                "content_id": value,
                "review_average_present": True,
                "review_count_present": True,
                "metadata_present": True,
            }
            for value in selected
        ],
        "error_classification": None,
    }


def failed_response(request: ProbeRequest, code: str):
    value = response(request)
    value.update(
        success=False,
        result_count=None,
        total_count=None,
        items=[],
        error_classification=code,
    )
    return value


def runner_result(
    *,
    success: bool = False,
    saved: bool = False,
    reason: str = "INTERNAL_RUNNER_ERROR",
):
    return RunnerResult(
        success, "rank", 1, 100, "2026-08-26T05:00:00Z",
        "rank-sorted population turnover", saved, False, None, None,
        2, None, None, None, None, None, None, None, None, (reason,),
    )


class TemporalProbeOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        DEFAULT_STATE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="orchestrator-", dir=DEFAULT_STATE_DIRECTORY
        )
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def execute(self, fetch=response, **kwargs):
        return orchestrator.run_orchestrator(
            captured_at=kwargs.pop("captured_at", FIRST),
            as_of=kwargs.pop("as_of", AS_OF),
            fetch_response=fetch,
            output_directory=self.directory,
            delay=kwargs.pop("delay", mock.Mock()),
            **kwargs,
        )

    def store_previous(self, values: list[str], request: ProbeRequest | None = None):
        selected = request or ProbeRequest("FANZA", "digital", "videoa", "rank", 1, 100)
        value = create_temporal_probe_state(
            captured_at=FIRST,
            site=selected.site,
            service=selected.service,
            floor=selected.floor,
            source_sort=selected.source_sort,
            offset=selected.offset,
            hits=selected.hits,
            content_ids=values,
        )
        self.assertTrue(
            write_temporal_probe_state(value, output_directory=self.directory).success
        )

    def test_a_fixed_four_population_plan(self):
        result = self.execute(dry_run=True, fetch=None)
        self.assertEqual(result.planned_count, 4)

    def test_b_plan_order_is_fixed(self):
        result = self.execute(dry_run=True, fetch=None)
        self.assertEqual(
            [(p.source_sort, p.offset, p.hits) for p in result.populations],
            [("rank", 1, 100), ("rank", 101, 100), ("review", 1, 100), ("review", 101, 100)],
        )

    def test_c_baseline_is_safe(self):
        result = self.execute()
        self.assertEqual(result.populations[0].reason, "BASELINE_CREATED")
        self.assertFalse(result.populations[0].comparison_available)

    def test_d_previous_state_enables_comparison(self):
        self.store_previous(ids())
        result = self.execute(captured_at=SECOND)
        self.assertTrue(result.populations[0].comparison_available)

    def test_e_comparison_metrics_are_forwarded(self):
        self.store_previous(ids(0, 2))
        result = self.execute(lambda request: response(request, ids(1, 2)), captured_at=SECOND)
        first = result.populations[0]
        self.assertEqual((first.retained_count, first.entered_count, first.exited_count), (1, 1, 1))

    def test_f_anonymous_ids_are_absent(self):
        self.assertNotIn("anonymous_item_ids", repr(self.execute().to_dict()))

    def test_g_raw_content_id_is_absent(self):
        raw = "sensitive-raw-content-id"
        result = self.execute(lambda request: response(request, [raw]))
        self.assertNotIn(raw, repr(result.to_dict()))

    def test_h_state_filename_is_basename(self):
        filename = self.execute().populations[0].state_filename
        self.assertEqual(filename, Path(filename).name)

    def test_i_first_success_continues(self):
        fetch = mock.Mock(side_effect=response)
        self.execute(fetch)
        self.assertGreater(fetch.call_count, 1)

    def test_j_four_successes_report_success(self):
        result = self.execute()
        self.assertEqual((result.overall_status, result.succeeded_count), ("SUCCESS", 4))

    def test_k_second_api_failure_skips_remaining(self):
        calls = 0
        def fetch(request):
            nonlocal calls
            calls += 1
            return failed_response(request, "API_ERROR") if calls == 2 else response(request)
        result = self.execute(fetch)
        self.assertEqual((result.executed_count, result.succeeded_count, result.failed_count, result.skipped_count), (2, 1, 1, 2))

    def test_l_rate_limit_stops_immediately(self):
        fetch = mock.Mock(side_effect=lambda request: failed_response(request, "RATE_LIMIT"))
        result = self.execute(fetch)
        self.assertEqual((fetch.call_count, result.stop_reason_code), (1, "RATE_LIMIT"))

    def test_m_adapter_failure_stops(self):
        result = self.execute(lambda request: {"malformed": True})
        self.assertEqual((result.executed_count, result.stop_reason_code), (1, "MALFORMED_RESPONSE"))

    def test_n_runner_failure_stops(self):
        result = self.execute(runner=mock.Mock(return_value=runner_result()))
        self.assertEqual(result.stop_reason_code, "RUNNER_FAILURE")

    def test_o_store_failure_stops(self):
        failed = runner_result(reason="STATE_CONFLICT")
        result = self.execute(runner=mock.Mock(return_value=failed))
        self.assertEqual(result.stop_reason_code, "STORE_FAILURE")

    def test_p_previous_ambiguity_stops(self):
        failed = runner_result(reason="AMBIGUOUS_PREVIOUS_STATE")
        result = self.execute(runner=mock.Mock(return_value=failed))
        self.assertEqual(result.stop_reason_code, "PREVIOUS_STATE_AMBIGUITY")

    def test_q_partial_success_counts(self):
        calls = 0
        def fetch(request):
            nonlocal calls
            calls += 1
            return {} if calls == 3 else response(request)
        result = self.execute(fetch)
        self.assertEqual((result.overall_status, result.executed_count, result.succeeded_count, result.failed_count, result.skipped_count), ("PARTIAL_FAILURE", 3, 2, 1, 1))

    def test_r_retry_is_zero(self):
        fetch = mock.Mock(return_value={})
        result = self.execute(fetch)
        self.assertEqual((fetch.call_count, result.retry_count), (1, 0))

    def test_s_unknown_population_is_rejected(self):
        unknown = RequestPlan((ProbeRequest("FANZA", "digital", "videoa", "date", 1, 100),), 1.0)
        with mock.patch.object(orchestrator, "build_request_plan", return_value=unknown):
            result = self.execute()
        self.assertEqual(result.populations[0].reason, "REQUEST_NOT_ALLOWED")

    def test_t_identity_mismatch_is_rejected(self):
        result = self.execute(lambda request: response(ProbeRequest("FANZA", "digital", "videoa", "rank", 101, 100)))
        self.assertEqual(result.stop_reason_code, "REQUEST_IDENTITY_MISMATCH")

    def test_u_internal_exception_is_safe(self):
        result = self.execute(mock.Mock(side_effect=RuntimeError("secret exception")))
        self.assertEqual(result.stop_reason_code, "INTERNAL_ORCHESTRATOR_ERROR")

    def test_v_dry_run_changes_no_files(self):
        before = set(self.directory.iterdir())
        self.execute(dry_run=True, fetch=None)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_w_dry_run_does_not_call_api(self):
        fetch = mock.Mock()
        self.execute(fetch, dry_run=True)
        fetch.assert_not_called()

    def test_x_none_metrics_are_not_zeroed(self):
        first = self.execute().populations[0]
        self.assertIsNone(first.retained_count)
        self.assertIsNone(first.jaccard)

    def test_y_absolute_path_is_absent(self):
        self.assertNotIn(str(self.directory), repr(self.execute().to_dict()))

    def test_z_traceback_and_exception_are_absent(self):
        result = self.execute(mock.Mock(side_effect=RuntimeError("raw secret traceback")))
        rendered = repr(result.to_dict()).lower()
        self.assertNotIn("traceback", rendered)
        self.assertNotIn("raw secret", rendered)

    def test_aa_delay_runs_between_requests_only(self):
        delay = mock.Mock()
        self.execute(delay=delay)
        self.assertEqual(delay.call_count, 3)

    def test_ab_read_back_failure_is_classified(self):
        failed = runner_result(reason="READ_BACK_VALIDATION_FAILED")
        result = self.execute(runner=mock.Mock(return_value=failed))
        self.assertEqual(result.stop_reason_code, "READ_BACK_VALIDATION_FAILURE")

    def test_ac_failed_first_population_reports_failure(self):
        result = self.execute(lambda request: {})
        self.assertEqual((result.overall_status, result.succeeded_count, result.failed_count), ("FAILURE", 0, 1))

    def test_ad_dry_run_exposes_policy_only(self):
        result = self.execute(dry_run=True, fetch=None)
        self.assertEqual((result.retry_count, result.stop_on_error, result.executed_count), (0, True, 0))


if __name__ == "__main__":
    unittest.main()
