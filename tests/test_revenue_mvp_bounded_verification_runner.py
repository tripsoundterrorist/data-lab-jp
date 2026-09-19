from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_bounded_live_verification as adapter  # noqa: E402
import revenue_mvp_bounded_verification_runner as runner  # noqa: E402
from revenue_mvp_lifecycle_receipt import public_item_id  # noqa: E402


PRIVATE_ID = "private-runner-fixture"
PUBLIC_ID = public_item_id("FANZA", "digital", "videoa", PRIVATE_ID)
KEY = "approval-bound-idempotency-0001"
NOW = datetime(2026, 9, 17, 2, 0, tzinfo=timezone.utc)


def approval(**changes):
    value = runner.LiveApproval(
        runner.APPROVAL_VERSION,
        runner.APPROVAL_SCOPE,
        "approval-fixture-0001",
        KEY,
        NOW - timedelta(minutes=1),
        NOW + timedelta(minutes=5),
        True,
        True,
    )
    return replace(value, **changes)


def payload():
    return {
        "result": {
            "status": 200,
            "result_count": 1,
            "items": [
                {
                    "content_id": PRIVATE_ID,
                    "affiliateURL": "https://affiliate.fanza.com/safe",
                    "title": "private title",
                }
            ],
        }
    }


def base(**changes):
    values = {
        "public_id": PUBLIC_ID,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "content_id": PRIVATE_ID,
        "idempotency_key": KEY,
    }
    values.update(changes)
    return values


def live(**changes):
    callbacks = {
        "secret_name_checker": mock.Mock(
            return_value={name: True for name in runner.REQUIRED_SECRET_NAMES}
        ),
        "claim_idempotency_once": mock.Mock(return_value=True),
        "claim_global_slot": mock.Mock(return_value=True),
        "release_global_slot": mock.Mock(return_value=True),
        "transport": mock.Mock(return_value=(200, payload())),
        "clock": mock.Mock(return_value=NOW),
        "sleeper": mock.Mock(),
    }
    for name in tuple(callbacks):
        if name in changes:
            callbacks[name] = changes.pop(name)
    result = runner.run_verification(
        **base(
            mode=adapter.LIVE,
            approval=changes.pop("approval", approval()),
            approval_evaluated_at=changes.pop("approval_evaluated_at", NOW),
            **callbacks,
            **changes,
        )
    )
    return result, callbacks


class BoundedVerificationRunnerTests(unittest.TestCase):
    def test_default_dry_run_calls_no_external_capability(self):
        callbacks = {
            name: mock.Mock()
            for name in (
                "secret_name_checker",
                "claim_idempotency_once",
                "claim_global_slot",
                "release_global_slot",
                "transport",
                "clock",
                "sleeper",
            )
        }
        result = runner.run_verification(**base(**callbacks))
        self.assertEqual(result.status, adapter.DRY_RUN_READY)
        self.assertIsNone(result.receipt)
        self.assertEqual(result.api_calls, 0)
        self.assertEqual(result.runner_writes, 0)
        for callback in callbacks.values():
            callback.assert_not_called()

    def test_missing_or_invalid_approval_blocks_before_secret_check(self):
        checker = mock.Mock()
        cases = (
            None,
            approval(scope="OTHER"),
            approval(one_shot=False),
            approval(live_execution_allowed=False),
            approval(expires_at=NOW),
            approval(issued_at=NOW + timedelta(seconds=1)),
            approval(expires_at=NOW + timedelta(minutes=16)),
            approval(idempotency_key="different-key-0001"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = runner.run_verification(
                    **base(
                        mode=adapter.LIVE,
                        approval=value,
                        approval_evaluated_at=NOW,
                        secret_name_checker=checker,
                        clock=mock.Mock(return_value=NOW),
                    )
                )
                self.assertEqual(result.status, adapter.BLOCKED)
                self.assertFalse(result.approval_valid)
        checker.assert_not_called()

    def test_stale_approval_evaluated_at_cannot_authorize_expired_live_run(self):
        checker = mock.Mock()
        transport = mock.Mock()
        result = runner.run_verification(
            **base(
                mode=adapter.LIVE,
                approval=approval(),
                approval_evaluated_at=NOW,
                secret_name_checker=checker,
                clock=mock.Mock(return_value=NOW + timedelta(minutes=6)),
                transport=transport,
            )
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertFalse(result.approval_valid)
        self.assertIn("APPROVAL_NOT_CURRENT", result.reason_codes)
        checker.assert_not_called()
        transport.assert_not_called()

    def test_pure_approval_contract_accepts_only_current_one_shot_scope(self):
        valid, reasons = runner.validate_live_approval(
            approval(), evaluated_at=NOW, expected_idempotency_key=KEY
        )
        self.assertTrue(valid)
        self.assertEqual(reasons, ())

    def test_secret_checker_receives_names_only_and_rejects_non_booleans(self):
        checker = mock.Mock(
            return_value={name: True for name in runner.REQUIRED_SECRET_NAMES}
        )
        result, _ = live(secret_name_checker=checker)
        self.assertEqual(result.status, adapter.VERIFIED)
        checker.assert_called_once_with(runner.REQUIRED_SECRET_NAMES)

        for returned in (
            {"DMM_API_ID": "private", "DMM_AFFILIATE_ID": True},
            {"DMM_API_ID": True},
            {"DMM_API_ID": True, "DMM_AFFILIATE_ID": False},
        ):
            with self.subTest(returned=returned):
                result, callbacks = live(
                    secret_name_checker=mock.Mock(return_value=returned)
                )
                self.assertEqual(result.status, adapter.BLOCKED)
                callbacks["claim_idempotency_once"].assert_not_called()

    def test_secret_checker_exception_fails_without_claim_or_transport(self):
        result, callbacks = live(
            secret_name_checker=mock.Mock(
                side_effect=RuntimeError("private secret value")
            )
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        callbacks["claim_idempotency_once"].assert_not_called()
        callbacks["transport"].assert_not_called()
        self.assertNotIn(
            "private secret value", json.dumps(result.to_safe_dict())
        )

    def test_approval_expiry_during_secret_check_blocks_before_claim(self):
        result, callbacks = live(
            clock=mock.Mock(
                side_effect=(NOW, NOW + timedelta(minutes=6))
            )
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertFalse(result.approval_valid)
        self.assertTrue(result.secret_names_confirmed)
        callbacks["claim_idempotency_once"].assert_not_called()
        callbacks["transport"].assert_not_called()

    def test_expiry_immediately_before_first_transport_releases_slot(self):
        clock = mock.Mock(
            side_effect=(
                NOW,
                NOW,
                NOW + timedelta(minutes=4, seconds=59),
                NOW + timedelta(minutes=6),
            )
        )
        result, callbacks = live(clock=clock)
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertIsNone(result.receipt)
        self.assertEqual(result.api_calls, 0)
        self.assertTrue(result.global_slot_claimed)
        self.assertTrue(result.global_slot_released)
        self.assertIn(
            "PRE_TRANSPORT_APPROVAL_NOT_CURRENT", result.reason_codes
        )
        callbacks["transport"].assert_not_called()
        callbacks["release_global_slot"].assert_called_once_with(KEY)

    def test_pre_transport_clock_failure_and_reversal_block_and_release(self):
        clocks = (
            mock.Mock(
                side_effect=(NOW, NOW, NOW, RuntimeError("private clock"))
            ),
            mock.Mock(
                side_effect=(
                    NOW,
                    NOW + timedelta(seconds=1),
                    NOW + timedelta(seconds=2),
                    NOW + timedelta(seconds=1),
                )
            ),
        )
        for clock in clocks:
            with self.subTest(clock=clock):
                result, callbacks = live(clock=clock)
                self.assertEqual(result.status, adapter.BLOCKED)
                self.assertEqual(result.api_calls, 0)
                self.assertTrue(result.global_slot_released)
                callbacks["transport"].assert_not_called()
                callbacks["release_global_slot"].assert_called_once_with(KEY)
                self.assertNotIn(
                    "private clock", json.dumps(result.to_safe_dict())
                )

    def test_retry_expiry_blocks_second_transport_and_releases_slot(self):
        expired = NOW + timedelta(minutes=6)
        clock_values = (NOW, NOW, NOW, NOW, NOW, NOW, expired, expired)
        transport = mock.Mock(
            side_effect=(
                adapter.BoundedTransportFailure("TRANSIENT"),
                (200, payload()),
            )
        )
        result, callbacks = live(
            clock=mock.Mock(side_effect=clock_values),
            transport=transport,
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertIsNone(result.receipt)
        self.assertEqual((result.api_calls, transport.call_count), (1, 1))
        self.assertTrue(result.global_slot_released)
        callbacks["sleeper"].assert_called_once()
        callbacks["release_global_slot"].assert_called_once_with(KEY)

    def test_retry_expiry_release_failure_remains_fail_closed(self):
        expired = NOW + timedelta(minutes=6)
        result, callbacks = live(
            clock=mock.Mock(
                side_effect=(NOW, NOW, NOW, NOW, NOW, NOW, expired, expired)
            ),
            transport=mock.Mock(
                side_effect=adapter.BoundedTransportFailure("TRANSIENT")
            ),
            release_global_slot=mock.Mock(return_value=False),
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertIsNone(result.receipt)
        self.assertEqual(result.api_calls, 1)
        self.assertTrue(result.global_slot_release_attempted)
        self.assertFalse(result.global_slot_released)
        callbacks["transport"].assert_called_once()
        callbacks["release_global_slot"].assert_called_once_with(KEY)

    def test_success_claims_once_releases_global_slot_and_returns_receipt(self):
        result, callbacks = live()
        self.assertEqual(result.status, adapter.VERIFIED)
        self.assertIsNotNone(result.receipt)
        self.assertTrue(result.approval_valid)
        self.assertTrue(result.secret_names_confirmed)
        self.assertTrue(result.idempotency_claimed)
        self.assertTrue(result.global_slot_claimed)
        self.assertTrue(result.global_slot_release_attempted)
        self.assertTrue(result.global_slot_released)
        self.assertFalse(result.eligibility_granted)
        callbacks["claim_idempotency_once"].assert_called_once_with(KEY)
        callbacks["claim_global_slot"].assert_called_once_with(KEY)
        callbacks["release_global_slot"].assert_called_once_with(KEY)
        callbacks["transport"].assert_called_once_with(PRIVATE_ID)

    def test_idempotency_or_global_claim_denial_never_calls_transport(self):
        result, callbacks = live(
            claim_idempotency_once=mock.Mock(return_value=False)
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        callbacks["claim_global_slot"].assert_not_called()
        callbacks["transport"].assert_not_called()
        callbacks["release_global_slot"].assert_not_called()

        result, callbacks = live(
            claim_global_slot=mock.Mock(return_value=False)
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        callbacks["transport"].assert_not_called()
        callbacks["release_global_slot"].assert_not_called()

    def test_claim_exceptions_fail_closed_without_raw_exception(self):
        for name in ("claim_idempotency_once", "claim_global_slot"):
            with self.subTest(name=name):
                result, callbacks = live(
                    **{
                        name: mock.Mock(
                            side_effect=RuntimeError("private claim detail")
                        )
                    }
                )
                self.assertEqual(result.status, adapter.FAIL_CLOSED)
                callbacks["transport"].assert_not_called()
                self.assertNotIn(
                    "private claim detail", json.dumps(result.to_safe_dict())
                )

    def test_release_false_or_exception_discards_receipt_and_fails_closed(self):
        releases = (
            mock.Mock(return_value=False),
            mock.Mock(side_effect=RuntimeError("private release detail")),
        )
        for release in releases:
            with self.subTest(release=release):
                result, callbacks = live(release_global_slot=release)
                self.assertEqual(result.status, adapter.FAIL_CLOSED)
                self.assertIsNone(result.receipt)
                self.assertTrue(result.global_slot_claimed)
                self.assertTrue(result.global_slot_release_attempted)
                self.assertFalse(result.global_slot_released)
                callbacks["transport"].assert_called_once()
                self.assertNotIn(
                    "private release detail", json.dumps(result.to_safe_dict())
                )

    def test_adapter_failure_after_global_claim_still_releases(self):
        result, callbacks = live(
            transport=mock.Mock(side_effect=RuntimeError("private raw response"))
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertTrue(result.global_slot_released)
        callbacks["release_global_slot"].assert_called_once_with(KEY)
        self.assertNotIn(
            "private raw response", json.dumps(result.to_safe_dict())
        )

    def test_safe_result_contains_no_private_or_approval_values(self):
        result, _ = live()
        rendered = json.dumps(result.to_safe_dict(), sort_keys=True)
        for forbidden in (
            PRIVATE_ID,
            KEY,
            "approval-fixture-0001",
            "affiliate.fanza.com",
            "api_id",
            "affiliate_id",
            "raw_response",
            "credential",
        ):
            self.assertNotIn(forbidden, rendered.casefold())

    def test_source_has_no_network_secret_storage_or_private_adapter_use(self):
        source = (
            ROOT / "scripts" / "revenue_mvp_bounded_verification_runner.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "urllib",
            "requests",
            "urlopen",
            "os.environ",
            ".env",
            "sqlite3",
            "open(",
            "write_text",
            "write_bytes",
            "adapter._",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
