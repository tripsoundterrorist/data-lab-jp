from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collection_policy import (  # noqa: E402
    PolicyStatus,
    ProductionEligibilityGates,
    date_policy,
    evaluate_collection_policy,
    rank_candidate_policy,
    review_candidate_policy,
)


class CollectionPolicyTests(unittest.TestCase):
    def assert_invalid(self, policy: object, reason: str) -> None:
        result = evaluate_collection_policy(policy)
        self.assertFalse(result.valid)
        self.assertFalse(result.production_collection_eligible)
        self.assertIn(reason, result.reason_codes)

    def test_a_date_existing_policy_is_valid(self) -> None:
        policy = date_policy()
        result = evaluate_collection_policy(policy)
        self.assertTrue(result.valid)
        self.assertTrue(result.production_collection_eligible)
        self.assertEqual((policy.hits, policy.offsets), (50, (1, 51)))

    def test_b_rank_candidate_is_valid_experimental_and_blocked(self) -> None:
        policy = rank_candidate_policy()
        result = evaluate_collection_policy(policy)
        self.assertTrue(result.valid)
        self.assertTrue(policy.experimental)
        self.assertEqual(result.candidate_total_items, 200)
        self.assertFalse(result.production_collection_eligible)

    def test_c_review_one_page_candidate(self) -> None:
        result = evaluate_collection_policy(review_candidate_policy())
        self.assertTrue(result.valid)
        self.assertEqual(result.candidate_total_items, 100)
        self.assertFalse(result.production_collection_eligible)

    def test_d_review_two_page_candidate(self) -> None:
        result = evaluate_collection_policy(
            review_candidate_policy(include_second_page=True)
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.candidate_total_items, 200)
        self.assertFalse(result.production_collection_eligible)

    def test_e_unconfirmed_official_definition_blocks_rank(self) -> None:
        policy = rank_candidate_policy()
        self.assertFalse(policy.eligibility_gates.official_sort_definition_confirmed)
        self.assertFalse(evaluate_collection_policy(policy).production_collection_eligible)

    def test_f_incomplete_and_even_complete_gates_do_not_promote_v01(self) -> None:
        incomplete = replace(
            rank_candidate_policy(),
            eligibility_gates=ProductionEligibilityGates(
                official_sort_definition_confirmed=True
            ),
        )
        complete = replace(
            rank_candidate_policy(),
            eligibility_gates=ProductionEligibilityGates(
                True, True, True, True, True, True, True
            ),
        )
        self.assertFalse(incomplete.eligibility_gates.all_confirmed())
        self.assertTrue(complete.eligibility_gates.all_confirmed())
        self.assertFalse(evaluate_collection_policy(incomplete).production_collection_eligible)
        self.assertFalse(evaluate_collection_policy(complete).production_collection_eligible)

    def test_g_unknown_sort_fails_closed(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), source_sort="new"), "UNKNOWN_SORT")

    def test_h_duplicate_offsets_are_invalid(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), offsets=(1, 1)), "DUPLICATE_OFFSETS")

    def test_i_nonpositive_offset_is_invalid(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), offsets=(0, 101)), "INVALID_OFFSETS")

    def test_j_nonpositive_hits_is_invalid(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), hits=0), "INVALID_HITS")

    def test_k_request_count_mismatch_is_invalid(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), max_requests_per_run=1), "REQUEST_BUDGET_MISMATCH")

    def test_l_experimental_retry_default_is_zero_and_nonzero_rejected(self) -> None:
        self.assertEqual(rank_candidate_policy().retry_count, 0)
        self.assert_invalid(replace(rank_candidate_policy(), retry_count=1), "EXPERIMENTAL_RETRY_FORBIDDEN")

    def test_m_rate_limit_stop_false_is_rejected(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), stop_on_rate_limit=False), "RATE_LIMIT_STOP_REQUIRED")

    def test_n_automatic_pagination_is_rejected(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), automatic_pagination=True), "AUTOMATIC_PAGINATION_FORBIDDEN")

    def test_o_review_body_is_rejected(self) -> None:
        self.assert_invalid(replace(review_candidate_policy(), review_body_requested=True), "REVIEW_BODY_FORBIDDEN")

    def test_p_global_rank_semantics_are_rejected(self) -> None:
        self.assert_invalid(replace(rank_candidate_policy(), position_semantics="global popularity rank"), "INVALID_RANK_SEMANTICS")

    def test_q_unconfirmed_review_order_semantics_are_rejected(self) -> None:
        self.assert_invalid(replace(review_candidate_policy(), review_sort_semantics="average descending"), "UNCONFIRMED_REVIEW_SEMANTICS")

    def test_r_internal_exception_fails_closed(self) -> None:
        with mock.patch("collection_policy._invalid_reasons", side_effect=RuntimeError):
            result = evaluate_collection_policy(rank_candidate_policy())
        self.assertFalse(result.valid)
        self.assertFalse(result.production_collection_eligible)
        self.assertEqual(result.reason_codes, ("INTERNAL_POLICY_ERROR",))


if __name__ == "__main__":
    unittest.main()
