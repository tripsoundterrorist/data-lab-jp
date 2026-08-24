from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_stability_policy as policy  # noqa: E402


CURRENT = datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc)


def comparison(
    *,
    retained: int = 80,
    previous: int = 100,
    current: int = 100,
    hours: float = 24,
    source_sort: str = "rank",
    offset: int = 1,
    hits: int = 100,
    history_count: int = 1,
):
    entered = current - retained
    exited = previous - retained
    union = previous + current - retained
    return policy.StabilityInput(
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        previous_captured_at=CURRENT - timedelta(hours=hours),
        current_captured_at=CURRENT,
        previous_count=previous,
        current_count=current,
        retained_count=retained,
        entered_count=entered,
        exited_count=exited,
        retention_rate=round(retained / previous, 6),
        entry_rate=round(entered / current, 6),
        exit_rate=round(exited / previous, 6),
        jaccard=round(retained / union, 6),
        turnover_rate=round((entered + exited) / union, 6),
        comparison_available=True,
        history_count=history_count,
    )


def baseline():
    return policy.StabilityInput(
        "rank", 1, 100, None, None,
        None, None, None, None, None, None, None, None, None, None,
        False, 0,
    )


class TemporalStabilityPolicyTests(unittest.TestCase):
    def assess(self, value=None):
        return policy.assess_temporal_stability(value or comparison())

    def test_a_baseline_is_insufficient_history(self):
        self.assertEqual(self.assess(baseline()).classification, policy.INSUFFICIENT_HISTORY)

    def test_b_day_two_is_observation_only(self):
        self.assertEqual(self.assess().classification, policy.OBSERVATION_ONLY)

    def test_c_retention_049_is_low(self):
        self.assertEqual(self.assess(comparison(retained=49)).observation_band, policy.LOW)

    def test_d_retention_050_is_moderate(self):
        self.assertEqual(self.assess(comparison(retained=50)).observation_band, policy.MODERATE)

    def test_e_retention_079_is_moderate(self):
        self.assertEqual(self.assess(comparison(retained=79)).observation_band, policy.MODERATE)

    def test_f_retention_080_is_high(self):
        self.assertEqual(self.assess(comparison(retained=80)).observation_band, policy.HIGH)

    def test_g_retention_one_is_high(self):
        self.assertEqual(self.assess(comparison(retained=100)).observation_band, policy.HIGH)

    def test_h_retention_zero_is_low(self):
        self.assertEqual(self.assess(comparison(retained=0)).observation_band, policy.LOW)

    def test_i_short_interval_has_no_band(self):
        result = self.assess(comparison(hours=11.99))
        self.assertEqual((result.classification, result.observation_band), (policy.ANOMALOUS_COMPARISON, policy.UNKNOWN))

    def test_j_twelve_hour_boundary_is_allowed(self):
        self.assertEqual(self.assess(comparison(hours=12)).classification, policy.OBSERVATION_ONLY)

    def test_k_twenty_four_hours_is_normal(self):
        self.assertEqual(self.assess().interval_hours, 24.0)

    def test_l_forty_eight_hour_boundary_is_allowed(self):
        self.assertEqual(self.assess(comparison(hours=48)).classification, policy.OBSERVATION_ONLY)

    def test_m_over_forty_eight_hours_is_separate(self):
        result = self.assess(comparison(hours=48.01))
        self.assertEqual(result.safe_reason_codes, ("DAY_INTERVAL_OUT_OF_RANGE",))

    def test_n_naive_timestamp_is_rejected(self):
        value = replace(comparison(), previous_captured_at=datetime(2026, 8, 25, 5, 0))
        self.assertEqual(self.assess(value).classification, policy.INVALID_INPUT)

    def test_o_non_increasing_timestamp_is_rejected(self):
        value = replace(comparison(), previous_captured_at=CURRENT)
        self.assertEqual(self.assess(value).safe_reason_codes, ("TIMESTAMP_ORDER_INVALID",))

    def test_p_retained_over_previous_is_anomalous(self):
        value = replace(comparison(), previous_count=79)
        self.assertEqual(self.assess(value).classification, policy.ANOMALOUS_COMPARISON)

    def test_q_retained_over_current_is_anomalous(self):
        value = replace(comparison(), current_count=79)
        self.assertEqual(self.assess(value).classification, policy.ANOMALOUS_COMPARISON)

    def test_r_entered_mismatch_is_anomalous(self):
        self.assertEqual(self.assess(replace(comparison(), entered_count=19)).classification, policy.ANOMALOUS_COMPARISON)

    def test_s_exited_mismatch_is_anomalous(self):
        self.assertEqual(self.assess(replace(comparison(), exited_count=19)).classification, policy.ANOMALOUS_COMPARISON)

    def test_t_jaccard_mismatch_is_anomalous(self):
        self.assertEqual(self.assess(replace(comparison(), jaccard=0.5)).classification, policy.ANOMALOUS_COMPARISON)

    def test_u_turnover_mismatch_is_anomalous(self):
        self.assertEqual(self.assess(replace(comparison(), turnover_rate=0.1)).classification, policy.ANOMALOUS_COMPARISON)

    def test_v_full_population_is_complete(self):
        self.assertTrue(self.assess().population_complete)

    def test_w_partial_population_is_safe(self):
        result = self.assess(comparison(previous=80, current=75, retained=60))
        self.assertEqual((result.classification, result.population_complete), (policy.OBSERVATION_ONLY, False))

    def test_x_count_over_hits_is_rejected(self):
        self.assertEqual(self.assess(comparison(previous=101, current=100, retained=80)).classification, policy.INVALID_INPUT)

    def test_y_zero_count_is_rejected(self):
        value = replace(comparison(), previous_count=0)
        self.assertEqual(self.assess(value).classification, policy.INVALID_INPUT)

    def test_z_rank_and_review_use_same_semantics(self):
        rank = self.assess(comparison(source_sort="rank"))
        review = self.assess(comparison(source_sort="review"))
        self.assertEqual((rank.classification, rank.observation_band), (review.classification, review.observation_band))

    def test_aa_unknown_sort_is_rejected(self):
        self.assertEqual(self.assess(comparison(source_sort="date")).classification, policy.INVALID_INPUT)

    def test_ab_unknown_offset_is_rejected(self):
        self.assertEqual(self.assess(comparison(offset=2)).classification, policy.INVALID_INPUT)

    def test_ac_hits_other_than_100_is_rejected(self):
        self.assertEqual(self.assess(comparison(hits=50)).classification, policy.INVALID_INPUT)

    def test_ad_one_comparison_is_not_evaluated(self):
        self.assertEqual(self.assess(comparison(history_count=1)).production_readiness, policy.NOT_EVALUATED)

    def test_ae_two_comparisons_are_not_evaluated(self):
        self.assertEqual(self.assess(comparison(history_count=2)).production_readiness, policy.NOT_EVALUATED)

    def test_af_three_comparisons_are_review_eligible(self):
        self.assertEqual(self.assess(comparison(history_count=3)).production_readiness, policy.REVIEW_ELIGIBLE)

    def test_ag_large_history_is_never_automatically_ready(self):
        result = self.assess(comparison(history_count=100))
        self.assertEqual(result.production_readiness, policy.REVIEW_ELIGIBLE)
        self.assertNotIn("READY", result.production_readiness)

    def test_ah_safe_output_contains_no_id_or_path(self):
        rendered = repr(self.assess().to_dict()).lower()
        for forbidden in ("content_id", "anonymous_item_ids", "title", "url", "path", "credential"):
            self.assertNotIn(forbidden, rendered)

    def test_ai_internal_exception_is_safe(self):
        with mock.patch.object(policy, "_assess", side_effect=RuntimeError("secret traceback")):
            result = policy.assess_temporal_stability(comparison())
        self.assertEqual(result.safe_reason_codes, ("INTERNAL_POLICY_ERROR",))
        self.assertNotIn("secret", repr(result.to_dict()))

    def test_aj_entry_rate_mismatch_is_anomalous(self):
        self.assertEqual(self.assess(replace(comparison(), entry_rate=0.1)).classification, policy.ANOMALOUS_COMPARISON)

    def test_ak_exit_rate_mismatch_is_anomalous(self):
        self.assertEqual(self.assess(replace(comparison(), exit_rate=0.1)).classification, policy.ANOMALOUS_COMPARISON)

    def test_al_iso_z_timestamps_are_supported(self):
        value = replace(comparison(), previous_captured_at="2026-08-25T05:00:00Z", current_captured_at="2026-08-26T05:00:00Z")
        self.assertEqual(self.assess(value).interval_hours, 24.0)

    def test_am_policy_constants_are_versioned(self):
        self.assertEqual((policy.POLICY_VERSION, policy.MIN_MEANINGFUL_INTERVAL_HOURS, policy.MAX_MEANINGFUL_INTERVAL_HOURS), ("0.1", 12.0, 48.0))


if __name__ == "__main__":
    unittest.main()
