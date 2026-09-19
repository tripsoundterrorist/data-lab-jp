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
from revenue_mvp_lifecycle_receipt import public_item_id  # noqa: E402


PRIVATE_ID = "private-fixture-id"
PUBLIC_ID = public_item_id("FANZA", "digital", "videoa", PRIVATE_ID)
NOW = datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc)


def payload(*, returned=PRIVATE_ID, affiliate="https://affiliate.fanza.com/link", count=1):
    items = [] if count == 0 else [
        {"content_id": returned, "affiliateURL": affiliate, "title": "private title"}
    ]
    return {"result": {"status": 200, "result_count": count, "items": items}}


def run(**changes):
    values = {
        "public_id": PUBLIC_ID,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "content_id": PRIVATE_ID,
        "idempotency_key": "verify-fixture-0001",
    }
    values.update(changes)
    return adapter.run_bounded_verification(**values)


def live(**changes):
    transport = changes.pop("transport", mock.Mock(return_value=(200, payload())))
    claim = changes.pop("claim_once", mock.Mock(return_value=True))
    global_claim = changes.pop("claim_global_slot", mock.Mock(return_value=True))
    pre_transport_guard = changes.pop(
        "pre_transport_guard", mock.Mock(return_value=True)
    )
    clock = changes.pop("clock", mock.Mock(return_value=NOW))
    sleeper = changes.pop("sleeper", mock.Mock())
    return run(
        mode=adapter.LIVE,
        explicit_live_approval=True,
        secrets_confirmed=True,
        transport=transport,
        claim_once=claim,
        claim_global_slot=global_claim,
        pre_transport_guard=pre_transport_guard,
        clock=clock,
        sleeper=sleeper,
        **changes,
    ), transport, claim, sleeper


class BoundedLiveVerificationTests(unittest.TestCase):
    def test_default_is_dry_run_with_zero_calls(self):
        transport, claim, global_claim, guard, clock, sleeper = (
            mock.Mock() for _ in range(6)
        )
        result = run(transport=transport, claim_once=claim,
                     claim_global_slot=global_claim, pre_transport_guard=guard,
                     clock=clock, sleeper=sleeper)
        self.assertEqual(result.status, adapter.DRY_RUN_READY)
        self.assertEqual(result.api_calls, 0)
        self.assertEqual(result.database_writes, 0)
        self.assertEqual(result.production_writes, 0)
        self.assertIsNone(result.receipt)
        for callback in (transport, claim, global_claim, guard, clock, sleeper):
            callback.assert_not_called()

    def test_pre_transport_guard_is_required_before_every_transport(self):
        transport = mock.Mock()
        result, _, _, _ = live(
            transport=transport,
            pre_transport_guard=mock.Mock(return_value=False),
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertEqual((result.request_attempts, result.api_calls), (0, 0))
        self.assertIn(
            "PRE_TRANSPORT_APPROVAL_NOT_CURRENT", result.reason_codes
        )
        transport.assert_not_called()

        result, _, _, _ = live(
            transport=transport,
            pre_transport_guard=mock.Mock(side_effect=RuntimeError("private")),
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertEqual((result.request_attempts, result.api_calls), (0, 0))
        self.assertIn("PRE_TRANSPORT_GUARD_FAILED", result.reason_codes)
        transport.assert_not_called()

        retry_transport = mock.Mock(
            side_effect=adapter.BoundedTransportFailure("TRANSIENT")
        )
        retry_guard = mock.Mock(side_effect=(True, False))
        result, _, _, sleeper = live(
            transport=retry_transport,
            pre_transport_guard=retry_guard,
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertEqual(retry_transport.call_count, 1)
        self.assertEqual(retry_guard.call_count, 2)
        sleeper.assert_called_once()

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
        self.assertTrue(result.receipt.freshness_confirmed)
        self.assertEqual(result.receipt.freshness_evaluated_at, NOW)
        self.assertEqual(
            result.receipt.freshness_max_age_seconds,
            adapter.MAX_FRESHNESS_AGE_SECONDS,
        )
        self.assertFalse(result.eligibility_granted)
        self.assertIn(
            "SANITIZED_RECEIPT_CREATED_NOT_ELIGIBILITY", result.reason_codes
        )
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
                {"content_id": PRIVATE_ID, "affiliateURL": "https://a.fanza.com/one"},
                {"content_id": "different-private-id", "affiliateURL": "https://a.fanza.com/two"},
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

    def test_untrusted_affiliate_strings_never_become_present(self):
        values = (
            " ", "https://affiliate.fanza.com/a b", "not-a-url",
            "http://affiliate.fanza.com/path", "https://evil.example/path",
            "https://user@affiliate.fanza.com/path", "javascript:alert(1)",
            "https://affiliate.fanza.com/path\nheader:value",
            "https://affiliate.fanza.com/path%0d%0aheader:value",
            "https://affiliate.fanza.com:444/path",
            "https://evil.invalid\\.dmm.com/a",
            "https://affiliate.fanza.com/a\u00a0b",
        )
        for value in values:
            with self.subTest(value=value):
                result, _, _, _ = live(
                    transport=mock.Mock(return_value=(200, payload(affiliate=value)))
                )
                self.assertIsNone(
                    result.receipt.observation.affiliate_link_observed
                )
                self.assertIn(
                    "AFFILIATE_URL_VALIDATION_FAILED",
                    result.receipt.observation.reason_codes,
                )
                self.assertNotIn(
                    "AFFILIATE_URL_VALIDATED",
                    result.receipt.observation.reason_codes,
                )

    def test_parser_difference_urls_are_excluded_by_builder_without_echo(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "parser_difference_builder",
            ROOT / "scripts" / "build-public-data.py",
        )
        builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = builder
        spec.loader.exec_module(builder)
        master = {1: {"public_id": PUBLIC_ID}}
        confidence = {
            1: {"observation_stats": {"last_observed_at": NOW.isoformat()}}
        }
        unsafe_values = (
            "https://evil.invalid\\.dmm.com/a",
            "https://affiliate.fanza.com/a\u00a0b",
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                result, _, _, _ = live(
                    transport=mock.Mock(
                        return_value=(200, payload(affiliate=value))
                    )
                )
                selected, excluded = (
                    builder.filter_master_items_by_lifecycle_receipts(
                        master,
                        confidence,
                        (result.receipt,),
                        evaluated_at=NOW,
                    )
                )
                self.assertEqual(selected, {})
                self.assertEqual(excluded, 1)
                safe = json.dumps(result.to_safe_dict(), ensure_ascii=False)
                self.assertNotIn(value, safe)

    def test_request_context_binding_blocks_swap_before_claim_or_transport(self):
        transport = mock.Mock()
        claim = mock.Mock()
        swapped_id = public_item_id(
            "FANZA", "digital", "videoa", "different-private-id"
        )
        result = run(
            public_id=swapped_id,
            transport=transport,
            claim_once=claim,
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertIsNone(result.receipt)
        self.assertEqual(result.api_calls, 0)
        claim.assert_not_called()
        transport.assert_not_called()
        for changes in (
            {"site": "DMM.com"},
            {"service": "other"},
            {"floor": "other"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(run(**changes).status, adapter.FAIL_CLOSED)

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

    def test_clock_reversal_and_expired_freshness_never_create_candidate_receipt(self):
        reversed_clock = mock.Mock(side_effect=(NOW, NOW, NOW.replace(hour=0)))
        result, _, _, _ = live(clock=reversed_clock)
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertIsNone(result.receipt)
        self.assertEqual(result.api_calls, 1)

        times = iter((NOW, NOW, NOW.replace(hour=1, minute=6)))
        result, _, _, _ = live(
            clock=lambda: next(times), freshness_max_age_seconds=300
        )
        self.assertEqual(result.status, adapter.VERIFIED)
        self.assertFalse(result.receipt.freshness_confirmed)
        self.assertIn("RECEIPT_FRESHNESS_NOT_CONFIRMED", result.reason_codes)

    def test_clock_cannot_reverse_across_retry_boundary(self):
        clock = mock.Mock(
            side_effect=(
                NOW,
                NOW,
                NOW,
                NOW.replace(hour=0),
            )
        )
        result, transport, _, _ = live(
            transport=mock.Mock(
                side_effect=adapter.BoundedTransportFailure("TRANSIENT")
            ),
            clock=clock,
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertIsNone(result.receipt)
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertEqual(transport.call_count, 1)

    def test_rate_limit_flag_survives_post_request_clock_failure(self):
        transports = (
            mock.Mock(return_value=(429, {})),
            mock.Mock(
                side_effect=adapter.BoundedTransportFailure("RATE_LIMIT")
            ),
        )
        for transport in transports:
            with self.subTest(transport=transport):
                result, _, _, _ = live(
                    transport=transport,
                    clock=mock.Mock(
                        side_effect=(NOW, RuntimeError("private"))
                    ),
                )
                self.assertEqual(result.status, adapter.FAIL_CLOSED)
                self.assertTrue(result.rate_limit_stopped)
                self.assertEqual(
                    (result.request_attempts, result.api_calls), (1, 1)
                )

    def test_builder_rechecks_staleness_at_consumption(self):
        result, _, _, _ = live()
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bounded_builder", ROOT / "scripts" / "build-public-data.py"
        )
        builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = builder
        spec.loader.exec_module(builder)
        master = {1: {"public_id": PUBLIC_ID}}
        confidence = {1: {"observation_stats": {"last_observed_at": NOW.isoformat()}}}
        selected, excluded = builder.filter_master_items_by_lifecycle_receipts(
            master,
            confidence,
            (result.receipt,),
            evaluated_at=NOW.replace(hour=1, minute=6),
        )
        self.assertEqual(selected, {})
        self.assertEqual(excluded, 1)

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

    def test_claim_exceptions_preserve_exact_state_without_transport(self):
        result, transport, _, _ = live(
            claim_once=mock.Mock(side_effect=RuntimeError("private"))
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertFalse(result.idempotency_claimed)
        self.assertFalse(result.global_slot_claimed)
        self.assertEqual((result.request_attempts, result.api_calls), (0, 0))
        transport.assert_not_called()

        result, transport, _, _ = live(
            claim_global_slot=mock.Mock(side_effect=RuntimeError("private"))
        )
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertTrue(result.idempotency_claimed)
        self.assertFalse(result.global_slot_claimed)
        self.assertEqual((result.request_attempts, result.api_calls), (0, 0))
        transport.assert_not_called()

    def test_global_concurrency_claim_is_a_live_blocker(self):
        transport = mock.Mock()
        result, _, _, _ = live(
            transport=transport,
            claim_global_slot=mock.Mock(return_value=False),
        )
        self.assertEqual(result.status, adapter.BLOCKED)
        self.assertTrue(result.idempotency_claimed)
        self.assertFalse(result.global_slot_claimed)
        self.assertEqual(result.api_calls, 0)
        transport.assert_not_called()

    def test_counters_survive_clock_transport_and_sleeper_failures(self):
        result, _, _, _ = live(clock=mock.Mock(side_effect=RuntimeError("private")))
        self.assertEqual((result.request_attempts, result.api_calls), (0, 0))
        self.assertTrue(result.idempotency_claimed)
        self.assertTrue(result.global_slot_claimed)

        result, _, _, _ = live(
            clock=mock.Mock(side_effect=(NOW, RuntimeError("private")))
        )
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertTrue(result.idempotency_claimed)

        result, _, _, _ = live(
            clock=mock.Mock(side_effect=(NOW, NOW, RuntimeError("private")))
        )
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertTrue(result.global_slot_claimed)

        result, _, _, _ = live(
            transport=mock.Mock(side_effect=RuntimeError("private"))
        )
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertTrue(result.idempotency_claimed)

        clock = mock.Mock(side_effect=(NOW, NOW, NOW))
        result, _, _, _ = live(
            transport=mock.Mock(
                side_effect=adapter.BoundedTransportFailure("TRANSIENT")
            ),
            sleeper=mock.Mock(side_effect=RuntimeError("private")),
            clock=clock,
        )
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertFalse(result.retry_performed)

    def test_second_attempt_clock_and_transport_failures_keep_exact_counters(self):
        transport = mock.Mock(
            side_effect=adapter.BoundedTransportFailure("TRANSIENT")
        )
        clock = mock.Mock(
            side_effect=(NOW, NOW, NOW, RuntimeError("private"))
        )
        result, _, _, _ = live(transport=transport, clock=clock)
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertEqual((result.request_attempts, result.api_calls), (1, 1))
        self.assertFalse(result.retry_performed)
        self.assertEqual(transport.call_count, 1)

        transport = mock.Mock(
            side_effect=(
                adapter.BoundedTransportFailure("TRANSIENT"),
                RuntimeError("private"),
            )
        )
        result, _, _, _ = live(transport=transport)
        self.assertEqual(result.status, adapter.FAIL_CLOSED)
        self.assertEqual((result.request_attempts, result.api_calls), (2, 2))
        self.assertTrue(result.retry_performed)
        self.assertEqual(transport.call_count, 2)

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
            "urllib.request", "requests", "urlopen", "os.environ", 'ROOT / ".env"',
            "sqlite3", "open(", "write_text", "write_bytes",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
