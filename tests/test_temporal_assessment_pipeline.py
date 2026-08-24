from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_assessment_pipeline as pipeline  # noqa: E402
import temporal_stability_policy as stability  # noqa: E402
from temporal_stability_policy import (  # noqa: E402
    HIGH, LOW, MODERATE, NOT_EVALUATED, OBSERVATION_ONLY,
    REVIEW_ELIGIBLE, StabilityAssessment,
)


CURRENT = datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc)


def population(
    identity,
    *,
    comparison: bool = False,
    retained: int = 80,
    success: bool | None = True,
    reason: str | None = None,
    hours: float = 24,
):
    source_sort, offset, hits = identity
    union = 200 - retained
    return {
        "source_sort": source_sort,
        "offset": offset,
        "hits": hits,
        "success": success,
        "result_count": 100 if success else None,
        "total_count": 50000 if success else None,
        "returned_count": 100 if success else None,
        "elapsed_ms": 25 if success is not None else None,
        "review_average_coverage": 100 if success else None,
        "review_count_coverage": 100 if success else None,
        "metadata_coverage": 100 if success else None,
        "duplicate_count": 0 if success else None,
        "state_saved": success is True,
        "state_filename": f"{source_sort}-offset{offset}.json" if success else None,
        "reason": reason or ("COMPARISON_CREATED" if comparison else "BASELINE_CREATED") if success else reason or "API_ERROR",
        "comparison_available": comparison if success else False,
        "previous_captured_at": (CURRENT - timedelta(hours=hours)).isoformat() if comparison else None,
        "current_captured_at": CURRENT.isoformat() if success else None,
        "previous_count": 100 if comparison else None,
        "current_count": 100 if success else None,
        "retained_count": retained if comparison else None,
        "entered_count": 100 - retained if comparison else None,
        "exited_count": 100 - retained if comparison else None,
        "retention_rate": retained / 100 if comparison else None,
        "entry_rate": (100 - retained) / 100 if comparison else None,
        "exit_rate": (100 - retained) / 100 if comparison else None,
        "jaccard": round(retained / union, 6) if comparison else None,
        "turnover_rate": round((200 - 2 * retained) / union, 6) if comparison else None,
    }


def result(populations=None, *, status="SUCCESS", planned=4, executed=None, succeeded=None, failed=0, skipped=None, stopped=False):
    values = list(populations if populations is not None else [population(identity) for identity in pipeline.FIXED_POPULATIONS])
    executed = len(values) if executed is None else executed
    succeeded = sum(item["success"] is True for item in values) if succeeded is None else succeeded
    skipped = planned - executed if skipped is None else skipped
    return {
        "overall_status": status,
        "planned_count": planned,
        "executed_count": executed,
        "succeeded_count": succeeded,
        "failed_count": failed,
        "skipped_count": skipped,
        "stopped_early": stopped,
        "stop_reason_code": "API_ERROR" if stopped else None,
        "retry_count": 0,
        "stop_on_error": True,
        "partial_success_policy": "PRESERVE_COMPLETED_STATES_STOP_REMAINING",
        "populations": values,
    }


def histories(count=0):
    return {identity: count for identity in pipeline.FIXED_POPULATIONS}


class TemporalAssessmentPipelineTests(unittest.TestCase):
    def assess(self, value=None, history=None):
        return pipeline.assess_orchestrator_result(
            value if value is not None else result(),
            history_counts=history if history is not None else histories(),
        )

    def comparisons(self, retained=80, hours=24):
        return result([population(identity, comparison=True, retained=retained, hours=hours) for identity in pipeline.FIXED_POPULATIONS])

    def test_a_four_population_normal_input(self):
        self.assertEqual(len(self.assess().populations), 4)

    def test_b_four_baselines_have_no_comparisons(self):
        output = self.assess()
        self.assertEqual((output.assessment_status, output.assessed_count), (pipeline.NO_COMPARISONS, 4))

    def test_c_day_two_valid_comparison(self):
        output = self.assess(self.comparisons(), histories(1))
        self.assertEqual(output.assessment_status, pipeline.OBSERVATIONS_AVAILABLE)

    def test_d_history_one_is_observation_only(self):
        first = self.assess(self.comparisons(), histories(1)).populations[0]
        self.assertEqual((first.classification, first.production_readiness), (OBSERVATION_ONLY, NOT_EVALUATED))

    def test_e_low_band_is_forwarded(self):
        self.assertEqual(self.assess(self.comparisons(49), histories(1)).populations[0].observation_band, LOW)

    def test_f_moderate_band_is_forwarded(self):
        self.assertEqual(self.assess(self.comparisons(50), histories(1)).populations[0].observation_band, MODERATE)

    def test_g_high_band_is_forwarded(self):
        self.assertEqual(self.assess(self.comparisons(80), histories(1)).populations[0].observation_band, HIGH)

    def test_h_history_three_is_review_eligible(self):
        self.assertEqual(self.assess(self.comparisons(), histories(3)).populations[0].production_readiness, REVIEW_ELIGIBLE)

    def test_i_history_ten_never_returns_ready(self):
        rendered = repr(self.assess(self.comparisons(), histories(10)).to_dict())
        self.assertNotIn("PRODUCTION_READY", rendered)

    def test_j_failed_population_is_not_assessed(self):
        values = [population(pipeline.FIXED_POPULATIONS[0], success=False, reason="API_ERROR")]
        output = self.assess(result(values, status="FAILURE", failed=1, stopped=True), {})
        self.assertEqual(output.populations[0].assessment_status, pipeline.NOT_ASSESSED)

    def test_k_skipped_population_is_not_run(self):
        values = [population(pipeline.FIXED_POPULATIONS[0], success=False, reason="API_ERROR")]
        output = self.assess(result(values, status="FAILURE", failed=1, stopped=True), {})
        self.assertEqual(output.populations[1].assessment_status, pipeline.NOT_RUN)

    def test_l_partial_assessment(self):
        values = [population(pipeline.FIXED_POPULATIONS[0], comparison=True), population(pipeline.FIXED_POPULATIONS[1], success=False, reason="API_ERROR")]
        output = self.assess(result(values, status="PARTIAL_FAILURE", failed=1, stopped=True), {pipeline.FIXED_POPULATIONS[0]: 1})
        self.assertEqual(output.assessment_status, pipeline.PARTIAL_ASSESSMENT)

    def test_m_one_anomaly_sets_safe_overall_anomaly(self):
        values = [population(identity, comparison=True) for identity in pipeline.FIXED_POPULATIONS]
        values[0]["jaccard"] = 0.1
        self.assertEqual(self.assess(result(values), histories(1)).assessment_status, pipeline.ASSESSMENT_ANOMALY)

    def test_n_short_interval_reason_is_forwarded(self):
        first = self.assess(self.comparisons(hours=11), histories(1)).populations[0]
        self.assertEqual(first.safe_reason_codes, ("INTERVAL_TOO_SHORT",))

    def test_o_long_interval_reason_is_forwarded(self):
        first = self.assess(self.comparisons(hours=49), histories(1)).populations[0]
        self.assertEqual(first.safe_reason_codes, ("DAY_INTERVAL_OUT_OF_RANGE",))

    def test_p_metric_inconsistency_is_fail_closed(self):
        values = [population(identity, comparison=True) for identity in pipeline.FIXED_POPULATIONS]
        values[0]["entered_count"] = 1
        self.assertEqual(self.assess(result(values), histories(1)).populations[0].classification, "ANOMALOUS_COMPARISON")

    def test_q_unknown_population_is_rejected(self):
        values = [population(("date", 1, 100))]
        self.assertEqual(self.assess(result(values, planned=4, skipped=3), {}).assessment_status, pipeline.ASSESSMENT_ANOMALY)

    def test_r_hits_other_than_100_is_rejected(self):
        values = [population(("rank", 1, 50))]
        self.assertEqual(self.assess(result(values, planned=4, skipped=3), {}).assessment_status, pipeline.ASSESSMENT_ANOMALY)

    def test_s_no_rank_review_average_exists(self):
        output = self.assess(self.comparisons(), histories(1)).to_dict()
        self.assertNotIn("average", output)

    def test_t_no_offset_average_exists(self):
        self.assertNotIn("average_retention", repr(self.assess(self.comparisons(), histories(1)).to_dict()))

    def test_u_no_overall_score_exists(self):
        self.assertNotIn("score", self.assess().to_dict())

    def test_v_no_popularity_semantics_exist(self):
        self.assertNotIn("popularity", repr(self.assess().to_dict()).lower())

    def test_w_content_id_leak_is_rejected(self):
        value = result(); value["content_id"] = "secret"
        self.assertEqual(self.assess(value).safe_reason_codes, ("ORCHESTRATOR_RESULT_INVALID",))

    def test_x_anonymous_id_leak_is_rejected(self):
        value = result(); value["populations"][0]["anonymous_item_ids"] = ["secret"]
        self.assertEqual(self.assess(value).assessment_status, pipeline.ASSESSMENT_ANOMALY)

    def test_y_url_and_path_leaks_are_rejected(self):
        for leaked in ("https://invalid.example", "C:/private/state.json"):
            value = result(); value["populations"][0]["state_filename"] = leaked
            with self.subTest(leaked=leaked):
                self.assertEqual(self.assess(value).assessment_status, pipeline.ASSESSMENT_ANOMALY)

    def test_z_raw_exception_is_not_returned(self):
        value = result(); value["partial_success_policy"] = "raw secret exception"
        self.assertNotIn("raw secret", repr(self.assess(value).to_dict()))

    def test_aa_none_comparison_metrics_are_not_zeroed(self):
        first = self.assess().populations[0]
        self.assertIsNone(first.retained_count)
        self.assertIsNone(first.retention_rate)

    def test_ab_policy_output_is_not_recalculated(self):
        supplied = StabilityAssessment(
            "0.1", "rank", 1, 100, True, 86400, 24.0,
            100, 100, 80, 20, 20, 0.123456, 0.5, 0.25, True,
            HIGH, OBSERVATION_ONLY, NOT_EVALUATED, ("QUERY_POPULATION_COMPOSITION_OBSERVATION",),
        )
        with mock.patch.object(pipeline, "assess_temporal_stability", return_value=supplied):
            first = self.assess(self.comparisons(), histories(1)).populations[0]
        self.assertEqual(first.retention_rate, 0.123456)

    def test_ac_output_is_deterministic(self):
        self.assertEqual(self.assess().to_dict(), self.assess().to_dict())

    def test_ad_internal_exception_is_safe(self):
        with mock.patch.object(pipeline, "_assess_pipeline", side_effect=RuntimeError("secret traceback")):
            output = self.assess()
        self.assertEqual(output.safe_reason_codes, ("INTERNAL_PIPELINE_ERROR",))
        self.assertNotIn("secret", repr(output.to_dict()))

    def test_ae_empty_result_is_safe(self):
        empty = result([], planned=0, executed=0, succeeded=0, skipped=0)
        output = self.assess(empty, {})
        self.assertEqual((output.assessment_status, output.planned_count), (pipeline.NO_COMPARISONS, 0))

    def test_af_stopped_early_is_safe(self):
        values = [population(pipeline.FIXED_POPULATIONS[0], success=False, reason="API_ERROR")]
        output = self.assess(result(values, status="FAILURE", failed=1, stopped=True), {})
        self.assertEqual((output.not_assessed_count, output.not_run_count), (1, 3))

    def test_ag_unknown_policy_classification_is_rejected(self):
        bad = replace(stability.assess_temporal_stability(stability.StabilityInput(
            "rank", 1, 100, CURRENT - timedelta(days=1), CURRENT,
            100, 100, 80, 20, 20, .8, .2, .2, round(80/120, 6), round(40/120, 6), True, 1,
        )), classification="STABLE")
        with mock.patch.object(pipeline, "assess_temporal_stability", return_value=bad):
            output = self.assess(self.comparisons(), histories(1))
        self.assertEqual(output.assessment_status, pipeline.ASSESSMENT_ANOMALY)

    def test_ah_unknown_readiness_is_rejected(self):
        base = stability.assess_temporal_stability(stability.StabilityInput(
            "rank", 1, 100, CURRENT - timedelta(days=1), CURRENT,
            100, 100, 80, 20, 20, .8, .2, .2, round(80/120, 6), round(40/120, 6), True, 1,
        ))
        with mock.patch.object(pipeline, "assess_temporal_stability", return_value=replace(base, production_readiness="READY")):
            output = self.assess(self.comparisons(), histories(1))
        self.assertEqual(output.assessment_status, pipeline.ASSESSMENT_ANOMALY)


if __name__ == "__main__":
    unittest.main()
