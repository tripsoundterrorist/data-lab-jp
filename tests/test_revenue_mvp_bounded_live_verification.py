from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_bounded_live_verification as adapter  # noqa: E402
from product_verification import Observation  # noqa: E402


PUBLIC_ID = "itm_0123456789abcdef01234567"
PRIVATE_ID = "private-fixture-id"
NOW = datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc)


def payload(*, returned=PRIVATE_ID, affiliate="https://private.invalid/link", count=1):
    items = [] if count == 0 else [
        {"content_id": returned, "affiliateURL": affiliate, "title": "private title"}
    ]
    return {"result": {"status": 200, "result_count": count, "items": items}}


def run(**changes):
    values = {
        "public_id": PUBLIC_ID,
        "content_id": PRIVATE_ID,
        "idempotency_key": "verify-fixture-0001",
    }
    values.update(changes)
    return adapter.run_bounded_verification(**values)


def live(**changes):
    transport = changes.pop("transport", mock.Mock(return_value=(200, payload())))
    claim = changes.pop("claim_once", mock.Mock(return_value=True))
    clock = changes.pop("clock", mock.Mock(return_value=NOW))
    sleeper = changes.pop("sleeper", mock.Mock())
    return run(
        mode=adapter.LIVE,
        explicit_live_approval=True,
        secrets_confirmed=True,
        transport=transport,
        claim_once=claim,
        clock=clock,
        sleeper=sleeper,
        **changes,
    ), transport, claim, sleeper


class BoundedLiveVerificationTests(unittest.TestCase):
    def test_default_is_dry_run_with_zero_calls(self):
        transport, claim, clock, sleeper = (mock.Mock() for _ in range(4))
        result = run(transport=transport, claim_once=claim, clock=clock, sleeper=sleeper)
        self.assertEqual(result.status, adapter.DRY_RUN_READY)
        self.assertEqual(result.api_calls, 0)
        self.assertEqual(result.database_writes, 0)
        self.assertEqual(result.production_writes, 0)
        self.assertIsNone(result.receipt)
        for callback in (transport, claim, clock, sleeper):
            callback.assert_not_called()

    def test_live_requires_separate_approval_and_secret_confirmation(self):
        result = run(mode=adapter.LIVE)
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertIn("LIVE_APPROVAL_REQUIRED", result.reason_codes)
        result = run(mode=adapter.LIVE, explicit_live_approval=True)
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertIn("SECRET_EXISTENCE_CONFIRMATION_REQUIRED", result.reason_codes)

    def test_exact_match_creates_sanitized_receipt(self):
        result, transport, claim, sleeper = live()
        self.assertEqual(result.status, adapter.VERIFIED)
        self.assertEqual(result.request_attempts, 1)
        self.assertIs(result.receipt.observation.observation, Observation.API_ITEM_VISIBLE)
        self.assertIs(result.receipt.observation.expected_content_id_match, True)
        self.assertIs(result.receipt.observation.affiliate_link_observed, True)
        self.assertEqual(result.receipt.public_id, PUBLIC_ID)
        transport.assert_called_once_with(PRIVATE_ID)
        claim.assert_called_once_with("verify-fixture-0001")
        sleeper.assert_not_called()
        rendered = json.dumps(result.to_safe_dict(), sort_keys=True)
        for forbidden in (PRIVATE_ID, "https://", "affiliateURL", "api_id", "affiliate_id"):
            self.assertNotIn(forbidden, rendered)

    def test_mismatch_absent_and_multiple_results_are_not_candidates(self):
        cases = (
            ((200, payload(returned="different-private-id")), Observation.CID_MISMATCH),
            ((200, payload(count=0)), Observation.API_ITEM_NOT_RETURNED),
            ((200, {"result": {"status": 200, "result_count": 2, "items": [
                {"content_id": PRIVATE_ID, "affiliateURL": "private-one"},
                {"content_id": "different-private-id", "affiliateURL": "private-two"},
            ]}}), Observation.MULTIPLE_ITEMS_RETURNED),
        )
        for response, expected in cases:
            with self.subTest(expected=expected):
                result, _, _, _ = live(transport=mock.Mock(return_value=response))
                self.assertIs(result.receipt.observation.observation, expected)
                self.assertIsNot(result.receipt.observation.affiliate_link_observed, True)

    def test_absent_or_malformed_affiliate_value_never_becomes_true(self):
        for affiliate, expected in ((None, False), ({"private": "value"}, None)):
            with self.subTest(affiliate=affiliate):
                result, _, _, _ = live(
                    transport=mock.Mock(return_value=(200, payload(affiliate=affiliate)))
                )
                self.assertIs(result.receipt.observation.affiliate_link_observed, expected)

    def test_rate_limit_stops_immediately_without_retry(self):
        transport = mock.Mock(return_value=(429, {"private": "raw"}))
        result, _, _, sleeper = live(transport=transport)
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertTrue(result.rate_limit_stopped)
        self.assertEqual(result.request_attempts, 1)
        self.assertIs(result.receipt.observation.observation, Observation.API_RATE_LIMITED)
        transport.assert_called_once()
        sleeper.assert_not_called()

    def test_transient_failure_retries_once_with_bounded_wait(self):
        transport = mock.Mock(side_effect=(
            adapter.BoundedTransportFailure("TRANSIENT"),
            (200, payload()),
        ))
        result, _, _, sleeper = live(
            transport=transport, retry_limit=1, retry_wait_seconds=5
        )
        self.assertEqual(result.status, adapter.VERIFIED)
        self.assertEqual(result.request_attempts, 2)
        self.assertTrue(result.retry_performed)
        self.assertEqual(transport.call_count, 2)
        sleeper.assert_called_once_with(5)

    def test_retry_and_concurrency_bounds_fail_closed(self):
        for changes in (
            {"item_limit": 2}, {"concurrency": 2}, {"retry_limit": 2},
            {"retry_wait_seconds": 0}, {"retry_wait_seconds": 301},
        ):
            with self.subTest(changes=changes):
                result = run(**changes)
                self.assertEqual(result.status, adapter.FAIL_CLOSED)
                self.assertEqual(result.api_calls, 0)

    def test_idempotency_duplicate_blocks_before_transport(self):
        transport = mock.Mock()
        result, _, claim, _ = live(
            transport=transport, claim_once=mock.Mock(return_value=False)
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertIn("IDEMPOTENCY_KEY_ALREADY_CLAIMED", result.reason_codes)
        claim.assert_called_once()
        transport.assert_not_called()

    def test_raw_exception_and_payload_never_cross_safe_result(self):
        transport = mock.Mock(side_effect=RuntimeError("private-secret raw URL https://x"))
        result, _, _, _ = live(transport=transport)
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        rendered = json.dumps(result.to_safe_dict(), sort_keys=True)
        for forbidden in ("private-secret", "https://", PRIVATE_ID):
            self.assertNotIn(forbidden, rendered)

    def test_source_has_no_http_secret_or_persistence_capability(self):
        source = (ROOT / "scripts" / "revenue_mvp_bounded_live_verification.py").read_text(encoding="utf-8")
        for forbidden in (
            "urllib", "requests", "urlopen", "os.environ", 'ROOT / ".env"',
            "sqlite3", "open(", "write_text", "write_bytes",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
