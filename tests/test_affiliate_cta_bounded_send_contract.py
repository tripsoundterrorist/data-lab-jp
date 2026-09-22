from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_approved_context as approved
import affiliate_cta_bounded_send_contract as bounded
import affiliate_cta_canary_offline_candidate as render
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_production_composition as composition
import affiliate_cta_runtime_inert_integration as route


NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)
IDS = tuple(f"itm_{number:024x}" for number in range(10))
CONTEXT = approved._make_test_context(IDS, lambda _value: None)


def payload(content_id):
    return {"result": {"status": 200, "items": [{
        "content_id": content_id,
        "affiliateURL": "https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F",
    }]}}


def build(executor=None, **changes):
    calls = []
    def transport(request):
        calls.append(request)
        return payload(request._content_id)
    values = dict(
        monotonic_clock=lambda: 0, deadline=10, executor=executor,
        timeout_ms=bounded.DEFAULT_TIMEOUT_MS,
    )
    values.update(changes)
    lifecycle = composition._build_offline_composition_for_test(
        CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)},
        transport, lambda: NOW, **values,
    )
    return lifecycle, calls


class BoundedSendContractTests(unittest.TestCase):
    def test_production_adapters_are_declared_but_disabled(self):
        self.assertIsNone(bounded.production_monotonic_clock())
        self.assertIsNone(bounded.production_bounded_executor())
        self.assertIsNone(bounded.ProductionMonotonicClock().now())
        self.assertIsNone(bounded.ProductionBoundedExecutor().execute(None, None, None, None))

    def test_completed_send_is_bounded_and_opaque(self):
        lifecycle, calls = build()
        observation = lifecycle.observe(IDS[0])
        self.assertIsNotNone(observation)
        self.assertEqual(len(calls), 1)
        self.assertEqual(repr(calls[0]), "<OpaqueProviderRequest>")

    def test_timeout_cancel_and_late_result_are_terminal_without_retry(self):
        for mode, expected_calls in (("TIMEOUT", 0), ("CANCELLED", 0), ("LATE_RESULT", 1)):
            with self.subTest(mode=mode):
                lifecycle, calls = build(bounded._FakeBoundedExecutorForTest(mode))
                self.assertIsNone(lifecycle.observe(IDS[0]))
                self.assertFalse(lifecycle.valid())
                self.assertIsNone(lifecycle.observe(IDS[1]))
                self.assertEqual(len(calls), expected_calls)

    def test_expired_or_revoked_lease_stops_before_send(self):
        with self.assertRaises(ValueError):
            build(monotonic_clock=lambda: 10, deadline=10)
        revoked, revoked_calls = build()
        revoked.revoke()
        self.assertIsNone(revoked.observe(IDS[0]))
        self.assertEqual(revoked_calls, [])

    def test_invalid_timeout_is_fail_closed_without_transport(self):
        for value in (True, False, 0, -1, float("inf"), bounded.MAX_TIMEOUT_MS + 1):
            with self.subTest(value=value):
                lifecycle, calls = build(timeout_ms=value)
                self.assertIsNone(lifecycle.observe(IDS[0]))
                self.assertEqual(calls, [])

    def test_public_entries_cannot_inject_bounded_send_controls(self):
        forbidden = {"executor", "timeout", "cancel", "clock", "send", "transport"}
        for entry in (click.decide, render.render, route.assess):
            with self.subTest(entry=entry.__name__):
                self.assertTrue(forbidden.isdisjoint(inspect.signature(entry).parameters))

    def test_outcomes_and_adapters_do_not_reveal_request_or_response(self):
        outcome = bounded._SendOutcome("COMPLETED", {"private": "value"})
        self.assertEqual(repr(outcome), "<BoundedSendOutcome>")
        self.assertNotIn("value", repr(bounded._FakeBoundedExecutorForTest()))


if __name__ == "__main__":
    unittest.main()
