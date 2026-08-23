from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from product_lifecycle import (  # noqa: E402
    LifecyclePolicy,
    LifecycleState,
    evaluate_product_lifecycle,
)


AS_OF = datetime(2026, 8, 23, 8, 0, tzinfo=timezone.utc)
POLICY = LifecyclePolicy(
    observation_recency_window=timedelta(days=2),
    verification_ttl=timedelta(days=3),
)


def timestamp(delta: timedelta) -> str:
    return (AS_OF + delta).isoformat().replace("+00:00", "Z")


def verification(
    result: str,
    *,
    verified_delta: timedelta = timedelta(hours=-1),
    reason: str = "EXPLICIT_CHECK",
) -> dict[str, object]:
    return {
        "verification_source": "AVAILABILITY_VERIFIER",
        "verified_at": timestamp(verified_delta),
        "verification_result": result,
        "verification_reason": reason,
        "source_status_code": None,
    }


class ProductLifecycleTests(unittest.TestCase):
    def test_a_recent_collector_observation_is_observed_only(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(hours=-2)),
            verification=None,
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.OBSERVED)
        self.assertFalse(result.lifecycle_eligible_for_publication)
        self.assertNotEqual(result.state, LifecycleState.CONFIRMED_AVAILABLE)

    def test_b_several_days_non_observation_is_not_unavailable(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(days=-4)),
            verification=None,
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.VERIFICATION_DUE)
        self.assertNotEqual(result.state, LifecycleState.CONFIRMED_UNAVAILABLE)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_c_long_non_observation_is_not_unavailable(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(days=-365)),
            verification=None,
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.VERIFICATION_DUE)
        self.assertNotEqual(result.state, LifecycleState.CONFIRMED_UNAVAILABLE)

    def test_d_explicit_available_verification_is_confirmed(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=verification("available"),
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.CONFIRMED_AVAILABLE)
        self.assertTrue(result.lifecycle_eligible_for_publication)
        self.assertIsNotNone(result.verification)

    def test_e_explicit_unavailable_verification_is_confirmed(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(hours=-1)),
            verification=verification("unavailable"),
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.CONFIRMED_UNAVAILABLE)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_f_verification_error_is_never_unavailable(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(days=-7)),
            verification=verification("verification_error"),
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.VERIFICATION_ERROR)
        self.assertNotEqual(result.state, LifecycleState.CONFIRMED_UNAVAILABLE)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_g_malformed_verification_fails_closed(self) -> None:
        malformed = verification("available")
        del malformed["verification_source"]
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=malformed,
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.UNKNOWN)
        self.assertIn("MALFORMED_VERIFICATION", result.reasons)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_h_expired_verification_is_due(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=verification("available", verified_delta=timedelta(days=-4)),
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.VERIFICATION_DUE)
        self.assertIn("VERIFICATION_EXPIRED", result.reasons)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_i_future_timestamp_is_rejected(self) -> None:
        observed_future = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(minutes=1)),
            verification=None,
            as_of=AS_OF,
            policy=POLICY,
        )
        verified_future = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=verification(
                "available", verified_delta=timedelta(minutes=1)
            ),
            as_of=AS_OF,
            policy=POLICY,
        )
        for result in (observed_future, verified_future):
            self.assertEqual(result.state, LifecycleState.UNKNOWN)
            self.assertIn("INVALID_TIMESTAMP", result.reasons)
            self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_j_unknown_verification_status_fails_closed(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=verification("sale_ended"),
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.UNKNOWN)
        self.assertIn("UNKNOWN_VERIFICATION_RESULT", result.reasons)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_k_collector_non_observation_never_becomes_unavailable(self) -> None:
        for age in (timedelta(days=3), timedelta(days=30), timedelta(days=1000)):
            with self.subTest(age=age):
                result = evaluate_product_lifecycle(
                    last_observed_at=timestamp(-age),
                    verification=None,
                    as_of=AS_OF,
                    policy=POLICY,
                )
                self.assertNotEqual(
                    result.state, LifecycleState.CONFIRMED_UNAVAILABLE
                )
                self.assertIn(
                    "COLLECTOR_NON_OBSERVATION_NOT_AVAILABILITY_SIGNAL",
                    result.reasons,
                )
                self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_pending_verification_is_not_publishable(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=verification("verification_pending"),
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.VERIFICATION_PENDING)
        self.assertFalse(result.lifecycle_eligible_for_publication)

    def test_provenance_is_safe_and_structured(self) -> None:
        evidence = verification("available")
        evidence["source_status_code"] = 200
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=evidence,
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(
            set(result.verification.to_dict()),
            {
                "verification_source",
                "verified_at",
                "verification_result",
                "verification_reason",
                "source_status_code",
            },
        )

    def test_extra_credential_field_is_rejected(self) -> None:
        evidence = verification("available")
        evidence["api_credential"] = "fixture-secret"
        result = evaluate_product_lifecycle(
            last_observed_at=None,
            verification=evidence,
            as_of=AS_OF,
            policy=POLICY,
        )
        self.assertEqual(result.state, LifecycleState.UNKNOWN)
        self.assertIn("MALFORMED_VERIFICATION", result.reasons)

    def test_invalid_policy_fails_closed(self) -> None:
        result = evaluate_product_lifecycle(
            last_observed_at=timestamp(timedelta(hours=-1)),
            verification=None,
            as_of=AS_OF,
            policy=LifecyclePolicy(
                observation_recency_window=timedelta(0),
                verification_ttl=timedelta(days=1),
            ),
        )
        self.assertEqual(result.state, LifecycleState.UNKNOWN)
        self.assertIn("INVALID_POLICY", result.reasons)


if __name__ == "__main__":
    unittest.main()
