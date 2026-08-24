from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import inspect
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_probe_retention as retention  # noqa: E402


NOW = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)
RANK_1 = ("FANZA", "digital", "videoa", "rank", 1, 100)
RANK_101 = ("FANZA", "digital", "videoa", "rank", 101, 100)
REVIEW_1 = ("FANZA", "digital", "videoa", "review", 1, 100)
REVIEW_101 = ("FANZA", "digital", "videoa", "review", 101, 100)


def state(
    days_ago: int,
    *,
    identity=RANK_1,
    name: str | None = None,
    digest: str = "a" * 64,
    valid: bool = True,
    issue: str | None = None,
    captured_at: datetime | None = None,
):
    timestamp = captured_at if captured_at is not None else NOW - timedelta(days=days_ago)
    filename = name or f"state-{identity[3]}-{identity[4]}-{days_ago}.json"
    return retention.StateMetadata(filename, identity, timestamp, digest, valid, issue)


def classifications(*values, allowed=None):
    result = retention.plan_retention(
        values,
        generated_at=NOW,
        allowed_populations=allowed,
    )
    return result, [item.classification for item in result.states]


class TemporalProbeRetentionTests(unittest.TestCase):
    def test_a_four_population_isolation(self):
        values = [state(1, identity=value) for value in (RANK_1, RANK_101, REVIEW_1, REVIEW_101)]
        result, _ = classifications(*values)
        self.assertEqual(len(result.population_summaries), 4)

    def test_b_within_45_days_is_hot(self):
        _, values = classifications(state(45))
        self.assertEqual(values, [retention.KEEP_HOT])

    def test_c_older_non_latest_is_rotation_candidate(self):
        _, values = classifications(state(60), state(50))
        self.assertEqual(values[0], retention.ELIGIBLE_FOR_FUTURE_ROTATION)

    def test_d_latest_previous_is_kept(self):
        _, values = classifications(state(70), state(60))
        self.assertEqual(values[1], retention.KEEP_LATEST)

    def test_e_old_latest_is_kept(self):
        _, values = classifications(state(90), state(80))
        self.assertEqual(values[-1], retention.KEEP_LATEST)

    def test_f_future_timestamp_is_rejected(self):
        _, values = classifications(state(-1))
        self.assertEqual(values, [retention.FUTURE_TIMESTAMP_REJECT])

    def test_g_malformed_state_requires_review(self):
        result = retention.plan_retention([{"bad": True}], generated_at=NOW)
        self.assertEqual((result.states[0].classification, result.manual_review_count), (retention.INVALID_IGNORE, 1))

    def test_h_conflicting_duplicate_timestamp_is_ambiguous(self):
        first = state(10, name="first.json", digest="a" * 64)
        second = state(10, name="second.json", digest="b" * 64)
        _, values = classifications(first, second)
        self.assertEqual(values, [retention.AMBIGUOUS, retention.AMBIGUOUS])

    def test_i_symlink_metadata_requires_review(self):
        _, values = classifications(state(1, valid=False, issue="SYMLINK"))
        self.assertEqual(values, [retention.INVALID_IGNORE])

    def test_j_unreadable_metadata_requires_review(self):
        result, values = classifications(state(1, valid=False, issue="UNREADABLE"))
        self.assertEqual((values[0], result.manual_review_count), (retention.INVALID_IGNORE, 1))

    def test_k_unknown_schema_requires_review(self):
        _, values = classifications(state(1, valid=False, issue="UNKNOWN_SCHEMA_VERSION"))
        self.assertEqual(values, [retention.INVALID_IGNORE])

    def test_l_exact_seven_day_anchor_is_planned(self):
        result, values = classifications(state(7), state(0))
        self.assertEqual((values[0], result.states[0].anchor_days), (retention.KEEP_ANCHOR_CANDIDATE, 7))

    def test_m_exact_thirty_day_anchor_is_planned(self):
        result, values = classifications(state(30), state(0))
        self.assertEqual((values[0], result.states[0].anchor_days), (retention.KEEP_ANCHOR_CANDIDATE, 30))

    def test_n_nearest_anchor_is_not_selected(self):
        result, values = classifications(state(8), state(0))
        self.assertEqual(values[0], retention.KEEP_HOT)
        self.assertIsNone(result.states[0].anchor_days)

    def test_o_other_population_is_not_an_anchor(self):
        _, values = classifications(state(7), state(0, identity=REVIEW_1))
        self.assertEqual(values[0], retention.KEEP_HOT)

    def test_p_rank_and_review_are_not_mixed(self):
        result, _ = classifications(state(1), state(1, identity=REVIEW_1))
        self.assertEqual({item.source_sort for item in result.population_summaries}, {"rank", "review"})

    def test_q_offsets_are_not_mixed(self):
        result, _ = classifications(state(1), state(1, identity=RANK_101))
        self.assertEqual({item.offset for item in result.population_summaries}, {1, 101})

    def test_r_safe_result_uses_basename(self):
        value = state(1, name="C:/unsafe/state.json")
        result, _ = classifications(value)
        self.assertEqual(result.states[0].filename, "state.json")

    def test_s_absolute_path_is_not_returned(self):
        result, _ = classifications(state(1, name="C:/private/state.json"))
        self.assertNotIn("C:/private", repr(result.to_dict()))

    def test_t_no_destructive_function_exists(self):
        names = {name.lower() for name, value in inspect.getmembers(retention) if callable(value)}
        self.assertFalse(names & {"delete", "unlink", "move", "rename", "archive", "compress"})

    def test_u_planning_has_no_filesystem_mutation(self):
        before = set(ROOT.iterdir())
        classifications(state(1))
        self.assertEqual(set(ROOT.iterdir()), before)

    def test_v_invalid_is_not_rotation_candidate(self):
        result, values = classifications(state(90, valid=False, issue="MALFORMED_SCHEMA"))
        self.assertEqual(values[0], retention.INVALID_IGNORE)
        self.assertEqual(result.future_rotation_candidate_count, 0)

    def test_w_latest_selection_is_deterministic(self):
        first, values_a = classifications(state(80), state(70))
        second, values_b = classifications(state(70), state(80))
        self.assertEqual(sorted(values_a), sorted(values_b))
        self.assertEqual(first.keep_count, second.keep_count)

    def test_x_same_timestamp_same_hash_is_not_ambiguous(self):
        _, values = classifications(state(10, name="a.json"), state(10, name="b.json"))
        self.assertNotIn(retention.AMBIGUOUS, values)

    def test_y_conflicting_duplicate_is_never_rotation_candidate(self):
        result, values = classifications(
            state(90, name="a.json", digest="a" * 64),
            state(90, name="b.json", digest="b" * 64),
        )
        self.assertNotIn(retention.ELIGIBLE_FOR_FUTURE_ROTATION, values)
        self.assertEqual(result.manual_review_count, 2)

    def test_z_empty_input_is_safe(self):
        result, values = classifications()
        self.assertTrue(result.success)
        self.assertEqual((result.total_states, values), (0, []))

    def test_aa_single_baseline_is_safe(self):
        result, values = classifications(state(1))
        self.assertEqual((result.keep_count, values), (1, [retention.KEEP_HOT]))

    def test_ab_policy_version_is_fixed(self):
        result, _ = classifications()
        self.assertEqual((retention.POLICY_VERSION, result.policy_version), ("0.1", "0.1"))

    def test_ac_generated_at_has_timezone(self):
        result, _ = classifications()
        self.assertTrue(result.generated_at.endswith("Z"))

    def test_ad_internal_exception_is_safe(self):
        class Broken:
            def __iter__(self):
                raise RuntimeError("secret traceback")
        result = retention.plan_retention(Broken(), generated_at=NOW)
        self.assertEqual((result.success, result.reason_code), (False, "INTERNAL_RETENTION_ERROR"))
        self.assertNotIn("secret", repr(result.to_dict()))

    def test_ae_identity_outside_allowlist_requires_review(self):
        result, values = classifications(state(1, identity=REVIEW_1), allowed=frozenset({RANK_1}))
        self.assertEqual((values[0], result.manual_review_count), (retention.IDENTITY_MISMATCH, 1))

    def test_af_timestamp_parse_failure_requires_review(self):
        value = retention.StateMetadata("bad-time.json", RANK_1, None, "a" * 64, False, "TIMESTAMP_PARSE_FAILURE")
        _, values = classifications(value)
        self.assertEqual(values, [retention.INVALID_IGNORE])

    def test_ag_hot_period_is_45_days(self):
        self.assertEqual(retention.HOT_RETENTION_DAYS, 45)

    def test_ah_comparison_policy_is_latest_previous(self):
        result, _ = classifications()
        self.assertEqual(result.comparison_policy, "LATEST_PREVIOUS")

    def test_ai_classification_priority_keeps_anchor_over_hot(self):
        _, values = classifications(state(7), state(0))
        self.assertEqual(values[0], retention.KEEP_ANCHOR_CANDIDATE)


if __name__ == "__main__":
    unittest.main()
