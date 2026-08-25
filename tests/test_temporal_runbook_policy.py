from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_runbook_policy as policy  # noqa: E402


class TemporalRunbookPolicyTests(unittest.TestCase):
    def test_a_version(self):
        self.assertEqual(policy.RUNBOOK_VERSION, "0.1")

    def test_b_day3_history_is_two(self):
        self.assertEqual(policy.assess_history_transition(previous_history_count=1, successful_comparisons=4, interval_hours=24).history_count, 2)

    def test_c_day3_not_evaluated(self):
        self.assertEqual(policy.assess_history_transition(previous_history_count=1, successful_comparisons=4, interval_hours=24).production_readiness, "NOT_EVALUATED")

    def test_d_day4_history_is_three(self):
        self.assertEqual(policy.assess_history_transition(previous_history_count=2, successful_comparisons=4, interval_hours=24).history_count, 3)

    def test_e_day4_review_eligible(self):
        self.assertEqual(policy.assess_history_transition(previous_history_count=2, successful_comparisons=4, interval_hours=24).production_readiness, "REVIEW_ELIGIBLE")

    def test_f_review_eligible_is_not_ready(self):
        self.assertNotEqual(policy.assess_history_transition(previous_history_count=2, successful_comparisons=4, interval_hours=24).production_readiness, "READY")

    def test_g_fixed_four_population(self):
        self.assertEqual(policy.FIXED_POPULATIONS, (("rank", 1, 100), ("rank", 101, 100), ("review", 1, 100), ("review", 101, 100)))

    def test_h_correct_plan_valid(self):
        self.assertTrue(policy.validate_run_plan(policy.FIXED_POPULATIONS)[0])

    def test_i_wrong_population_rejected(self):
        self.assertFalse(policy.validate_run_plan(policy.FIXED_POPULATIONS[:-1])[0])

    def test_j_retry_zero(self):
        self.assertTrue(policy.validate_run_plan(policy.FIXED_POPULATIONS, retry_count=0)[0])

    def test_k_retry_rejected(self):
        self.assertFalse(policy.validate_run_plan(policy.FIXED_POPULATIONS, retry_count=1)[0])

    def test_l_stop_on_error(self):
        self.assertTrue(policy.STOP_ON_ERROR)

    def test_m_no_stop_rejected(self):
        self.assertFalse(policy.validate_run_plan(policy.FIXED_POPULATIONS, stop_on_error=False)[0])

    def test_n_request_interval_minimum(self):
        self.assertTrue(policy.validate_run_plan(policy.FIXED_POPULATIONS, request_interval_seconds=1)[0])

    def test_o_short_request_interval_rejected(self):
        self.assertFalse(policy.validate_run_plan(policy.FIXED_POPULATIONS, request_interval_seconds=.99)[0])

    def test_p_under_twelve_hours_rejected(self):
        self.assertFalse(policy.assess_history_transition(previous_history_count=1, successful_comparisons=4, interval_hours=11.99).valid)

    def test_q_over_forty_eight_hours_rejected(self):
        self.assertFalse(policy.assess_history_transition(previous_history_count=1, successful_comparisons=4, interval_hours=48.01).valid)

    def test_r_twenty_four_hours_valid(self):
        self.assertTrue(policy.assess_history_transition(previous_history_count=1, successful_comparisons=4, interval_hours=24).valid)

    def test_s_partial_success_is_preserved(self):
        result = policy.assess_history_transition(previous_history_count=1, successful_comparisons=3, interval_hours=24)
        self.assertIn("PRESERVE_COMPLETED_STATES_STOP_REMAINING", result.reason_codes)

    def test_t_partial_success_does_not_increment(self):
        self.assertEqual(policy.assess_history_transition(previous_history_count=1, successful_comparisons=3, interval_hours=24).history_count, 1)

    def test_u_no_rollback(self):
        self.assertTrue(policy.NO_ROLLBACK)

    def test_v_population_average_not_exposed(self):
        self.assertNotIn("average", repr(policy.RunbookCheck.__annotations__).lower())

    def test_w_publication_unlock_forbidden(self):
        self.assertFalse(policy.PUBLICATION_UNLOCK_ALLOWED)

    def test_x_lifecycle_unlock_forbidden(self):
        self.assertFalse(policy.LIFECYCLE_UNLOCK_ALLOWED)

    def test_y_semantics_unlock_forbidden(self):
        self.assertFalse(policy.SEMANTICS_UNLOCK_ALLOWED)

    def test_z_retention_is_45_days_keep_hot(self):
        self.assertEqual((policy.HOT_RETENTION_DAYS, policy.KEEP_HOT), (45, "KEEP_HOT"))

    def test_aa_unknown_state_fails_closed(self):
        result = policy.assess_history_transition(previous_history_count="1", successful_comparisons=4, interval_hours=24)
        self.assertEqual((result.valid, result.reason_codes), (False, ("UNKNOWN_STATE",)))

    def test_ab_execution_chain_fixed(self):
        self.assertEqual(policy.EXECUTION_CHAIN, ("ORCHESTRATOR", "ADAPTER", "RUNNER", "STATE_STORE", "COMPARISON", "STABILITY_POLICY", "ASSESSMENT_PIPELINE"))

    def test_ac_success_is_observation_only(self):
        self.assertEqual(policy.assess_history_transition(previous_history_count=1, successful_comparisons=4, interval_hours=24).classification, "OBSERVATION_ONLY")

    def test_ad_boolean_inputs_rejected(self):
        self.assertFalse(policy.assess_history_transition(previous_history_count=True, successful_comparisons=4, interval_hours=24).valid)


if __name__ == "__main__":
    unittest.main()
