from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock

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


class RecordingExecutor(bounded._FakeBoundedExecutorForTest):
    __slots__ = ("budgets", "calls")

    def __init__(self, **changes):
        super().__init__(**changes)
        self.budgets = []
        self.calls = 0

    def execute(self, request, timeout_ms, cancelled, send, pre_send):
        self.calls += 1
        self.budgets.append(timeout_ms)
        return super().execute(request, timeout_ms, cancelled, send, pre_send)


def route_args():
    return dict(
        version=route.VERSION, method="GET", path="/go/" + IDS[0], request_body_present=False,
        official_answer_candidate=True, publication_gate_overall_eligible=True,
        runtime_chain_connected=True, rate_limit_allowed=True, pr_disclosure_available=True,
        evaluated_at=NOW,
    )


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
        for value in (True, False, 0, -1, float("nan"), float("inf"), float("-inf"), bounded.MAX_TIMEOUT_MS + 1):
            with self.subTest(value=value):
                lifecycle, calls = build(timeout_ms=value)
                self.assertIsNone(lifecycle.observe(IDS[0]))
                self.assertEqual(calls, [])

    def test_remaining_budget_caps_configured_timeout_before_send(self):
        for timeout_ms, now, deadline, expected in (
            (bounded.MAX_TIMEOUT_MS, 0, 10, bounded.MAX_TIMEOUT_MS),
            (bounded.MAX_TIMEOUT_MS, 0, 1, 1_000),
            (1_000, 0, 1, 1_000),
            (5, 0, 10, 5),
            (bounded.MAX_TIMEOUT_MS, 9.9981, 10, 1),
            (bounded.MAX_TIMEOUT_MS, 0, 0.009, 8),
        ):
            with self.subTest(timeout_ms=timeout_ms, now=now, deadline=deadline):
                executor = RecordingExecutor()
                lifecycle, calls = build(executor, timeout_ms=timeout_ms,
                                         monotonic_clock=lambda: now, deadline=deadline)
                self.assertIsNotNone(lifecycle.observe(IDS[0]))
                self.assertEqual(executor.budgets, [expected])
                self.assertEqual(len(calls), 1)

    def test_sub_millisecond_or_expired_remaining_budget_starts_zero_sends(self):
        for now, deadline in ((9.9999, 10), (10, 10), (11, 10)):
            with self.subTest(now=now, deadline=deadline):
                executor = RecordingExecutor()
                if now >= deadline:
                    with self.assertRaises(ValueError):
                        build(executor, timeout_ms=bounded.MAX_TIMEOUT_MS,
                              monotonic_clock=lambda: now, deadline=deadline)
                    calls = []
                else:
                    lifecycle, calls = build(executor, timeout_ms=bounded.MAX_TIMEOUT_MS,
                                             monotonic_clock=lambda: now, deadline=deadline)
                    self.assertIsNone(lifecycle.observe(IDS[0]))
                self.assertEqual(executor.calls, 0)
                self.assertEqual(calls, [])

    def test_invalid_monotonic_values_are_terminal_before_send(self):
        for now in (float("nan"), float("inf"), float("-inf"), True, False):
            with self.subTest(now=now):
                executor = RecordingExecutor()
                with self.assertRaises(ValueError):
                    build(executor, monotonic_clock=lambda: now)
                self.assertEqual(executor.calls, 0)

    def test_elapsed_boundary_and_late_completion_are_terminal(self):
        for elapsed_ms, allowed in ((0.5, True), (1, False), (2, False)):
            with self.subTest(elapsed_ms=elapsed_ms):
                time = [0]
                def monotonic_clock():
                    return time[0]
                calls = []
                def transport(request):
                    calls.append(request)
                    time[0] += elapsed_ms / 1_000
                    return payload(request._content_id)
                executor = RecordingExecutor(elapsed_ms=elapsed_ms)
                lifecycle = composition._build_offline_composition_for_test(
                    CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)},
                    transport, lambda: NOW, monotonic_clock=monotonic_clock,
                    deadline=10, executor=executor, timeout_ms=1,
                )
                observation = lifecycle.observe(IDS[0])
                self.assertEqual(observation is not None, allowed)
                self.assertEqual(executor.calls, 1)
                self.assertEqual(len(calls), 1)
                if not allowed:
                    self.assertFalse(lifecycle.valid())
                    self.assertIsNone(lifecycle.observe(IDS[1]))
                    self.assertEqual(executor.calls, 1)

    def test_trusted_clock_after_return_rejects_completion_past_deadline(self):
        time = [0.99]
        executor = RecordingExecutor(elapsed_ms=0)
        calls = []
        def transport(request):
            calls.append(request)
            time[0] = 1
            return payload(request._content_id)
        lifecycle = composition._build_offline_composition_for_test(
            CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)}, transport,
            lambda: NOW, monotonic_clock=lambda: time[0], deadline=1, executor=executor, timeout_ms=1,
        )
        self.assertIsNone(lifecycle.observe(IDS[0]))
        self.assertEqual(executor.calls, 1)
        self.assertEqual(len(calls), 1)

    def test_public_click_route_render_reject_elapsed_timeout_and_stop_after_one_send(self):
        for entry in ("click", "route", "render"):
            with self.subTest(entry=entry):
                time = [0]
                calls = []
                def transport(request):
                    calls.append(request)
                    time[0] += 0.01
                    return payload(request._content_id)
                lifecycle = composition._build_offline_composition_for_test(
                    CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)}, transport,
                    lambda: NOW, monotonic_clock=lambda: time[0], deadline=1, timeout_ms=1,
                )
                with mock.patch.object(composition, "production_provider", return_value=lifecycle):
                    if entry == "click":
                        self.assertEqual(click.decide(version=click.VERSION, clicked_public_id=IDS[0], evaluated_at=NOW).status, click.BLOCKED)
                    elif entry == "route":
                        self.assertEqual(route.assess(**route_args()).status, route.BLOCKED)
                    else:
                        with self.assertRaises(ValueError):
                            render.render(as_of=NOW)
                self.assertEqual(len(calls), 1)

    def test_public_entries_reject_reported_elapsed_that_hides_trusted_elapsed(self):
        for entry in ("click", "route", "render"):
            with self.subTest(entry=entry):
                time = [0]
                calls = []
                def monotonic_clock():
                    return time[0]
                def transport(request):
                    calls.append(request)
                    time[0] += 0.01
                    return payload(request._content_id)
                lifecycle = composition._build_offline_composition_for_test(
                    CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)}, transport,
                    lambda: NOW, monotonic_clock=monotonic_clock, deadline=1,
                    executor=RecordingExecutor(elapsed_ms=0), timeout_ms=1,
                )
                with mock.patch.object(composition, "production_provider", return_value=lifecycle):
                    if entry == "click":
                        self.assertEqual(click.decide(version=click.VERSION, clicked_public_id=IDS[0], evaluated_at=NOW).status, click.BLOCKED)
                    elif entry == "route":
                        self.assertEqual(route.assess(**route_args()).status, route.BLOCKED)
                    else:
                        with self.assertRaises(ValueError):
                            render.render(as_of=NOW)
                self.assertEqual(len(calls), 1)
                self.assertFalse(lifecycle.valid())

    def test_clock_callback_sub_millisecond_before_marker_starts_zero_sends(self):
        class Clock:
            calls = 0
            def __call__(self):
                self.calls += 1
                return 0.9999 if self.calls >= 5 else 0
        clock = Clock()
        calls = []
        lifecycle = composition._build_offline_composition_for_test(
            CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)},
            lambda request: calls.append(request), lambda: NOW,
            monotonic_clock=clock, deadline=1, timeout_ms=1_000,
        )
        self.assertIsNone(lifecycle.observe(IDS[0]))
        self.assertEqual(calls, [])
        self.assertFalse(lifecycle.valid())

    def test_executor_clock_callback_revoke_before_marker_starts_zero_sends(self):
        holder = {}
        class Clock:
            calls = 0
            def __call__(self):
                self.calls += 1
                if self.calls == 6:
                    holder["lifecycle"].revoke()
                return 0
        clock = Clock()
        calls = []
        lifecycle = composition._build_offline_composition_for_test(
            CONTEXT, {value: f"content-{index}" for index, value in enumerate(IDS)},
            lambda request: calls.append(request), lambda: NOW,
            monotonic_clock=clock, deadline=1, timeout_ms=1_000,
        )
        holder["lifecycle"] = lifecycle
        self.assertIsNone(lifecycle.observe(IDS[0]))
        self.assertEqual(calls, [])
        self.assertFalse(lifecycle.valid())

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
