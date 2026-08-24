from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lifecycle_decision import (  # noqa: E402
    DecisionState,
    ReverificationContext,
    ReverificationPolicy,
    evaluate_lifecycle_decision,
)
from product_verification import Observation, VerificationObservation  # noqa: E402


NOW = datetime(2026, 8, 23, 8, 0, tzinfo=timezone.utc)


def observed(
    observation: Observation = Observation.API_ITEM_VISIBLE,
    *,
    affiliate: bool | None = None,
) -> VerificationObservation:
    return VerificationObservation(
        observation=observation,
        observed_at=NOW,
        expected_content_id_match=None,
        affiliate_link_observed=affiliate,
        source_status_code=200,
        reason_codes=("FIXTURE",),
    )


class LifecycleDecisionTests(unittest.TestCase):
    def assert_closed(self, result: object) -> None:
        self.assertFalse(result.publication_lifecycle_eligible)

    def test_a_visible_is_observation_only(self) -> None:
        result = evaluate_lifecycle_decision(observed())
        self.assertEqual(result.decision_state, DecisionState.OBSERVATION_ACCEPTED)
        self.assert_closed(result)

    def test_b_not_returned_requires_reverification(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.API_ITEM_NOT_RETURNED))
        self.assertEqual(result.decision_state, DecisionState.REVERIFY_REQUIRED)
        self.assertTrue(result.requires_reverification)

    def test_c_rate_limit_is_temporary(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.API_RATE_LIMITED))
        self.assertEqual(result.decision_state, DecisionState.TEMPORARY_FAILURE)

    def test_d_api_error_is_temporary(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.API_ERROR))
        self.assertEqual(result.decision_state, DecisionState.TEMPORARY_FAILURE)

    def test_e_cid_mismatch_is_anomaly(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.CID_MISMATCH))
        self.assertEqual(result.decision_state, DecisionState.OBSERVATION_ANOMALY)

    def test_f_multiple_items_is_anomaly(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.MULTIPLE_ITEMS_RETURNED))
        self.assertEqual(result.decision_state, DecisionState.OBSERVATION_ANOMALY)

    def test_g_malformed_response_is_anomaly(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.MALFORMED_RESPONSE))
        self.assertEqual(result.decision_state, DecisionState.OBSERVATION_ANOMALY)

    def test_h_unknown_stays_unknown(self) -> None:
        result = evaluate_lifecycle_decision(observed(Observation.UNKNOWN))
        self.assertEqual(result.decision_state, DecisionState.UNKNOWN)
        self.assert_closed(result)

    def test_i_affiliate_link_true_assigns_no_business_meaning(self) -> None:
        result = evaluate_lifecycle_decision(observed(affiliate=True))
        self.assert_closed(result)
        self.assertNotIn("affiliate", result.to_dict())

    def test_j_affiliate_link_false_assigns_no_business_meaning(self) -> None:
        result = evaluate_lifecycle_decision(observed(affiliate=False))
        self.assert_closed(result)
        self.assertNotIn("affiliate", result.to_dict())

    def test_k_unconfirmed_policy_always_blocks_publication(self) -> None:
        result = evaluate_lifecycle_decision(observed())
        self.assertFalse(result.official_policy_confirmed)
        self.assert_closed(result)

    def test_l_unknown_observation_type_fails_closed(self) -> None:
        fixture = replace(observed(), observation="NEW_SOURCE_STATE")  # type: ignore[arg-type]
        result = evaluate_lifecycle_decision(fixture)
        self.assertEqual(result.decision_state, DecisionState.UNKNOWN)
        self.assertIn("UNKNOWN_OBSERVATION_TYPE", result.reason_codes)
        self.assert_closed(result)

    def test_m_internal_exception_fails_closed(self) -> None:
        with mock.patch("lifecycle_decision._valid_policy_and_context", side_effect=RuntimeError):
            result = evaluate_lifecycle_decision(observed())
        self.assertEqual(result.decision_state, DecisionState.UNKNOWN)
        self.assertEqual(result.reason_codes, ("INTERNAL_DECISION_ERROR",))
        self.assert_closed(result)

    def test_n_invalid_reverification_policy_fails_closed(self) -> None:
        result = evaluate_lifecycle_decision(
            observed(),
            reverification_policy=ReverificationPolicy(
                minimum_consecutive_not_returned=0,
                grace_period=timedelta(0),
            ),
        )
        self.assertEqual(result.decision_state, DecisionState.UNKNOWN)
        self.assertIn("INVALID_REVERIFICATION_POLICY", result.reason_codes)
        self.assert_closed(result)

    def test_o_non_return_count_never_establishes_business_meaning(self) -> None:
        for count in (1, 3, 100):
            with self.subTest(count=count):
                result = evaluate_lifecycle_decision(
                    observed(Observation.API_ITEM_NOT_RETURNED),
                    reverification_context=ReverificationContext(
                        first_not_returned_at=NOW - timedelta(days=30),
                        consecutive_not_returned_count=count,
                        last_successful_visibility_at=NOW - timedelta(days=31),
                        next_verification_due_at=NOW + timedelta(days=1),
                    ),
                )
                self.assertEqual(result.decision_state, DecisionState.REVERIFY_REQUIRED)
                self.assert_closed(result)

    def test_confirmed_gate_still_requires_a_new_policy_version(self) -> None:
        result = evaluate_lifecycle_decision(
            observed(), official_policy_confirmed=True
        )
        self.assertEqual(result.decision_state, DecisionState.POLICY_BLOCKED)
        self.assert_closed(result)

    def test_contract_does_not_generate_prohibited_vocabulary(self) -> None:
        prohibited = {
            "SALE_ENDED",
            "UNPUBLISHED",
            "DELETED",
            "AFFILIATE_INELIGIBLE",
            "CONFIRMED_AVAILABLE",
            "CONFIRMED_UNAVAILABLE",
        }
        source = (ROOT / "scripts" / "lifecycle_decision.py").read_text(encoding="utf-8")
        results = [
            evaluate_lifecycle_decision(observed(value)).to_dict()
            for value in Observation
        ]
        rendered = source + repr(results)
        for word in prohibited:
            self.assertNotIn(word, rendered)


if __name__ == "__main__":
    unittest.main()
