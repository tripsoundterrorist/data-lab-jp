from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import collection_policy  # noqa: E402
import temporal_manual_review as review  # noqa: E402


POPULATIONS = (("rank", 1, 100), ("rank", 101, 100), ("review", 1, 100), ("review", 101, 100))


def comparison(retention=.8, *, timestamp="2026-08-24T14:00:00Z", hours=24, band=None):
    retained = round(retention * 100)
    entered = exited = 100 - retained
    union = 200 - retained
    return {
        "captured_at": timestamp,
        "interval_hours": hours,
        "previous_count": 100,
        "current_count": 100,
        "retained_count": retained,
        "entered_count": entered,
        "exited_count": exited,
        "retention_rate": retention,
        "jaccard": round(retained / union, 6),
        "turnover_rate": round((entered + exited) / union, 6),
        "observation_band": band or ("LOW" if retention < .5 else "MODERATE" if retention < .8 else "HIGH"),
        "classification": "OBSERVATION_ONLY",
        "production_readiness": "REVIEW_ELIGIBLE",
    }


def series(values=(.8, .8, .8)):
    return [comparison(value, timestamp=f"2026-08-{24 + index:02d}T14:00:00Z") for index, value in enumerate(values)]


def assess(*, population=POPULATIONS[0], history=3, values=(.8, .8, .8), comparisons=None, version="0.1", semantics="PENDING"):
    return review.review_temporal_population(
        review_policy_version=version,
        population=population,
        history_count=history,
        comparisons=series(values) if comparisons is None else comparisons,
        official_semantics_status=semantics,
    )


class TemporalManualReviewTests(unittest.TestCase):
    def test_a_version(self): self.assertEqual(review.REVIEW_POLICY_VERSION, "0.1")
    def test_b_history1_not_eligible(self): self.assertEqual(assess(history=1).outcome, review.NOT_REVIEW_ELIGIBLE)
    def test_c_history2_not_eligible(self): self.assertEqual(assess(history=2).outcome, review.NOT_REVIEW_ELIGIBLE)
    def test_d_history3_eligible(self): self.assertTrue(assess().review_eligible)
    def test_e_history4_eligible(self): self.assertTrue(assess(history=4).review_eligible)
    def test_f_valid_three_internal_candidate(self): self.assertEqual(assess().outcome, review.INTERNAL_CANDIDATE)
    def test_g_range_boundary_020(self): self.assertEqual(assess(values=(.6, .8, .7)).composition_consistency, review.ACCEPTABLE)
    def test_h_range_over_020(self): self.assertEqual(assess(values=(.59, .8, .7)).composition_consistency, review.VARIABLE)
    def test_i_high_high_high_acceptable(self): self.assertEqual(assess(values=(.8, .9, 1)).composition_consistency, review.ACCEPTABLE)
    def test_j_moderate_all_acceptable(self): self.assertEqual(assess(values=(.5, .6, .7)).composition_consistency, review.ACCEPTABLE)
    def test_k_high_low_high_variable(self): self.assertEqual(assess(values=(.8, .4, .8)).outcome, review.INSUFFICIENT_CONSISTENCY)

    def test_l_interval_under_12_hold(self):
        values = series(); values[0]["interval_hours"] = 11.99
        self.assertEqual(assess(comparisons=values).outcome, review.HOLD_FOR_ANOMALY)

    def test_m_interval_over_48_hold(self):
        values = series(); values[0]["interval_hours"] = 48.01
        self.assertEqual(assess(comparisons=values).outcome, review.HOLD_FOR_ANOMALY)

    def test_n_anomaly_hold(self):
        values = series(); values[0]["classification"] = "ANOMALOUS_COMPARISON"
        self.assertEqual(assess(comparisons=values).outcome, review.NOT_REVIEW_ELIGIBLE)

    def test_o_metric_inconsistency_hold(self):
        values = series(); values[0]["entered_count"] = 1
        self.assertEqual(assess(comparisons=values).outcome, review.HOLD_FOR_ANOMALY)

    def test_p_missing_comparison(self): self.assertEqual(assess(comparisons=series()[:2]).outcome, review.NOT_REVIEW_ELIGIBLE)

    def test_q_duplicate_timestamp(self):
        values = series(); values[1]["captured_at"] = values[0]["captured_at"]
        self.assertIn("DUPLICATE_COMPARISON_TIMESTAMP", assess(comparisons=values).reason_codes)

    def test_r_unknown_population(self): self.assertEqual(assess(population=("date", 1, 100)).outcome, review.MANUAL_REVIEW_REQUIRED)
    def test_s_hits_not_100(self): self.assertEqual(assess(population=("rank", 1, 50)).outcome, review.MANUAL_REVIEW_REQUIRED)
    def test_t_rank_offset1_isolated(self): self.assertEqual(assess(population=POPULATIONS[0]).source_sort, "rank")
    def test_u_rank_offset101_isolated(self): self.assertEqual(assess(population=POPULATIONS[1]).offset, 101)
    def test_v_review_offset1_isolated(self): self.assertEqual(assess(population=POPULATIONS[2]).source_sort, "review")
    def test_w_review_offset101_isolated(self): self.assertEqual(assess(population=POPULATIONS[3]).offset, 101)
    def test_x_population_average_absent(self): self.assertNotIn("average", assess().to_dict())
    def test_y_overall_score_absent(self): self.assertNotIn("overall_score", assess().to_dict())
    def test_z_internal_candidate_not_ready(self): self.assertNotEqual(assess().outcome, "READY")
    def test_aa_internal_candidate_not_production_eligible(self): self.assertNotIn("production_collection_eligible", assess().to_dict())
    def test_ab_pending_semantics_allows_internal_candidate(self): self.assertEqual(assess(semantics="PENDING").outcome, review.INTERNAL_CANDIDATE)
    def test_ac_pending_semantics_forbids_public_claim(self): self.assertIn("PUBLIC_INTERPRETATION_FORBIDDEN", assess().reason_codes)
    def test_ad_pending_semantics_is_retained(self): self.assertEqual(assess().official_semantics_status, "PENDING")
    def test_ae_lifecycle_not_an_input(self): self.assertNotIn("lifecycle", review.review_temporal_population.__annotations__)

    def test_af_collection_policy_remains_blocked(self):
        self.assertFalse(collection_policy.evaluate_collection_policy(collection_policy.rank_candidate_policy()).production_collection_eligible)

    def test_ag_promotion_candidate_does_not_unlock_gate(self):
        result = assess().to_dict(); self.assertTrue(result["promotion_candidate"]); self.assertNotIn("gate_unlock", result)

    def test_ah_raw_content_id_rejected(self):
        values = series(); values[0]["content_id"] = "x"
        self.assertIn("FORBIDDEN_REVIEW_INPUT", assess(comparisons=values).reason_codes)

    def test_ai_anonymous_id_rejected(self):
        values = series(); values[0]["anonymous_item_ids"] = ["x"]
        self.assertIn("FORBIDDEN_REVIEW_INPUT", assess(comparisons=values).reason_codes)

    def test_aj_url_rejected(self):
        values = series(); values[0]["url"] = "https://example.invalid"
        self.assertIn("FORBIDDEN_REVIEW_INPUT", assess(comparisons=values).reason_codes)

    def test_ak_path_rejected(self):
        values = series(); values[0]["absolute_path"] = "C:/secret"
        self.assertIn("FORBIDDEN_REVIEW_INPUT", assess(comparisons=values).reason_codes)

    def test_al_secret_rejected(self):
        values = series(); values[0]["credential"] = "secret"
        self.assertIn("FORBIDDEN_REVIEW_INPUT", assess(comparisons=values).reason_codes)

    def test_am_raw_exception_rejected(self):
        values = series(); values[0]["raw_exception"] = "trace"
        self.assertIn("FORBIDDEN_REVIEW_INPUT", assess(comparisons=values).reason_codes)

    def test_an_reason_codes_deterministic(self): self.assertEqual(assess().reason_codes, tuple(sorted(assess().reason_codes)))

    def test_ao_internal_exception_safe(self):
        with mock.patch.object(review, "_review", side_effect=RuntimeError("secret traceback")):
            result = assess()
        self.assertEqual(result.reason_codes, ("INTERNAL_REVIEW_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))

    def test_ap_unknown_version_fail_closed(self): self.assertEqual(assess(version="9").outcome, review.MANUAL_REVIEW_REQUIRED)
    def test_aq_empty_history_safe(self): self.assertEqual(assess(comparisons=[]).outcome, review.NOT_REVIEW_ELIGIBLE)
    def test_ar_contradictory_history(self): self.assertIn("CONTRADICTORY_HISTORY_COUNT", assess(history=3, comparisons=series() + [comparison(timestamp="2026-08-27T14:00:00Z")]).reason_codes)

    def test_as_unknown_band_hold(self):
        values = series(); values[0]["observation_band"] = "EXTREME"
        self.assertIn("UNKNOWN_OBSERVATION_BAND", assess(comparisons=values).reason_codes)

    def test_at_band_mismatch_hold(self):
        values = series(); values[0]["observation_band"] = "LOW"
        self.assertIn("OBSERVATION_BAND_MISMATCH", assess(comparisons=values).reason_codes)

    def test_au_unknown_semantics_fail_closed(self): self.assertEqual(assess(semantics="UNKNOWN").outcome, review.MANUAL_REVIEW_REQUIRED)
    def test_av_confirmed_semantics_still_only_candidate(self): self.assertEqual(assess(semantics="CONFIRMED").outcome, review.INTERNAL_CANDIDATE)
    def test_aw_no_raw_state_in_result(self): self.assertNotIn("raw", repr(assess().to_dict()).lower())
    def test_ax_threshold_has_no_business_label(self): self.assertEqual(review.CONSISTENCY_THRESHOLD, .20)


if __name__ == "__main__":
    unittest.main()
