"""Public-entry offline regressions for lease propagation and finalization."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import traceback
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_production_composition as composition
import affiliate_cta_offline_provider_factory as factory
import affiliate_cta_pretransport_safety as safety
import affiliate_cta_kill_deadline_contract as lease_module
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_runtime_inert_integration as route
import affiliate_cta_canary_offline_candidate as render

NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)
IDS = tuple(f"itm_{i:024x}" for i in range(10))
TARGET = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"
SOURCE = "".join(f"{pid}\tcontent-{i}\n" for i, pid in enumerate(IDS)).encode("ascii")
ARTIFACT = b"offline-fixture"


class Fixture:
    def __init__(self, **changes):
        self.time = 0
        self.calls = []
        self.clock_calls = 0
        self.on_transport = lambda: None
        self.on_clock = lambda: None
        self.wall_time = NOW
        base = approved._make_test_context(IDS, lambda _: None)
        inputs = dict(context=base, transport=self.transport, clock=self.clock,
                      monotonic_clock=lambda: self.time, deadline=10,
                      source_bytes=SOURCE, artifact_bytes=ARTIFACT,
                      expected_source_sha256=hashlib.sha256(SOURCE).hexdigest(),
                      expected_artifact_sha256=hashlib.sha256(ARTIFACT).hexdigest())
        inputs.update(changes)
        self.life = safety._build_fake_lifecycle_for_test(**inputs)

    def transport(self, request):
        self.calls.append(request._content_id)
        self.on_transport()
        return {"result": {"status": 200, "items": [
            {"content_id": request._content_id, "affiliateURL": TARGET}]}}

    def clock(self):
        self.clock_calls += 1
        self.on_clock()
        return self.wall_time

    def stop(self, mode):
        if mode == "revoke":
            self.life.revoke()
        else:
            self.time = 10

    @contextmanager
    def installed(self):
        with mock.patch.object(composition, "production_provider", return_value=self.life) as root:
            yield root


def public_click():
    return click.decide(version=click.VERSION, clicked_public_id=IDS[0], evaluated_at=NOW)


def route_args():
    return dict(version=route.VERSION, method="GET", path="/go/" + IDS[0],
                request_body_present=False, official_answer_candidate=True,
                publication_gate_overall_eligible=True, runtime_chain_connected=True,
                rate_limit_allowed=True, pr_disclosure_available=True, evaluated_at=NOW)


def public_route():
    return route.assess(**route_args())


class LeaseIntegrationTests(unittest.TestCase):
    def assert_closed(self, entry):
        if entry == "render":
            with self.assertRaises(ValueError):
                render.render(as_of=NOW)
        else:
            result = public_click() if entry == "click" else public_route()
            self.assertEqual(result.status, "BLOCKED")

    def test_normal_public_paths_share_one_context_provider_lease(self):
        f = Fixture()
        with f.installed() as root:
            decision = public_click()
            self.assertEqual(root.call_count, 1)
            root.reset_mock()
            routed = public_route()
            self.assertEqual(root.call_count, 1)
            root.reset_mock()
            rendered = render.render(as_of=NOW)
            self.assertEqual(root.call_count, 1)
        self.assertEqual(decision.status, click.ALLOWED)
        self.assertEqual(routed.status, route.READY)
        self.assertEqual(rendered.cta_count, 10)
        self.assertEqual(f.calls[-10:], [f"content-{i}" for i in range(10)])
        self.assertIs(f.life.context, f.life.provider.context)
        self.assertIs(f.life.lease, f.life.context.lease)
        self.assertIs(f.life.generation, f.life.provider.generation)
        for output in (decision.to_dict(), routed.to_dict()):
            for name, value in output.items():
                if name.endswith("allowed") or name.endswith("performed"):
                    self.assertIs(value, False)
        self.assertFalse(rendered.publication_allowed)
        self.assertFalse(rendered.affiliate_eligibility_allowed)
        self.assertFalse(rendered.gate_mutation_allowed)
        self.assertFalse(rendered.cta_activation_allowed)

    def test_provider_clock_revocation_and_expiry_block_click_and_route(self):
        for mode in ("revoke", "expire"):
            for entry in ("click", "route"):
                with self.subTest(mode=mode, entry=entry):
                    f = Fixture()
                    f.on_clock = lambda: f.stop(mode)
                    with f.installed():
                        self.assert_closed(entry)
                        self.assert_closed(entry)
                    self.assertEqual(len(f.calls), 1)

    def test_revocation_during_binding_prevents_build(self):
        original = lease_module._LifecycleLease.bind
        def bind(lease, context, provider):
            result = original(lease, context, provider)
            lease.revoke()
            return result
        with mock.patch.object(lease_module._LifecycleLease, "bind", autospec=True, side_effect=bind):
            f = Fixture()
        self.assertIsNone(f.life)
        self.assertEqual(f.calls, [])

    def test_observation_completion_and_batch_completion_recheck_lease(self):
        original = approved._observation_bound
        for mode in ("revoke", "expire"):
            f = Fixture()
            def bound(observation, context, provider):
                # Called immediately after the atomic observation was created.
                f.stop(mode)
                return original(observation, context, provider)
            with f.installed(), mock.patch.object(approved, "_observation_bound", side_effect=bound):
                self.assert_closed("click")
            self.assertEqual(len(f.calls), 1)
            f = Fixture()
            make_record = approved._InternalPresentationRecord
            def record(*args, **kwargs):
                value = make_record(*args, **kwargs)
                if len(f.calls) == 10:
                    f.stop(mode)
                return value
            # The provider finishes its last record before batch validation;
            # the public renderer must receive no tuple and return no HTML.
            with f.installed(), mock.patch.object(approved, "_InternalPresentationRecord", side_effect=record):
                self.assert_closed("render")
            self.assertEqual(len(f.calls), 10)

    def test_error_rate_limit_and_malformed_first_or_middle_stop_batch(self):
        for kind in ("exception", "rate_limit", "malformed"):
            for stop_at in (1, 4):
                f = Fixture()
                def transport(request):
                    response = f.transport(request)
                    if len(f.calls) == stop_at:
                        if kind == "exception":
                            raise TimeoutError("private-marker")
                        if kind == "rate_limit":
                            return {"result": {"status": 429, "items": []}}
                        return {"result": None}
                    return response
                f.life = safety._build_fake_lifecycle_for_test(
                    context=approved._make_test_context(IDS, lambda _: None),
                    transport=transport, clock=f.clock, monotonic_clock=lambda: f.time, deadline=10,
                    source_bytes=SOURCE, artifact_bytes=ARTIFACT,
                    expected_source_sha256=hashlib.sha256(SOURCE).hexdigest(),
                    expected_artifact_sha256=hashlib.sha256(ARTIFACT).hexdigest())
                with f.installed():
                    self.assert_closed("render")
                    self.assert_closed("click")
                self.assertEqual(len(f.calls), stop_at)

    def test_render_first_middle_last_clock_stop_returns_no_html(self):
        for mode in ("revoke", "expire"):
            for stop_at in (1, 4, 10):
                with self.subTest(mode=mode, stop_at=stop_at):
                    f = Fixture()
                    def hook():
                        if f.clock_calls == stop_at:
                            f.stop(mode)
                    f.on_clock = hook
                    with f.installed():
                        self.assert_closed("render")
                        self.assert_closed("click")
                    self.assertEqual(len(f.calls), stop_at)

    def test_stop_before_first_and_after_transport_never_retries(self):
        for mode in ("revoke", "expire"):
            for entry in ("click", "route", "render"):
                for before in (True, False):
                    with self.subTest(mode=mode, entry=entry, before=before):
                        f = Fixture()
                        if before:
                            f.stop(mode)
                        else:
                            f.on_transport = lambda: f.stop(mode)
                        with f.installed():
                            self.assert_closed(entry)
                            f.time = 0
                            self.assert_closed(entry)
                        self.assertEqual(len(f.calls), 0 if before else 1)

    def test_snapshot_stop_is_checked_before_provider_clock(self):
        original = factory._freeze
        for mode in ("revoke", "expire"):
            f = Fixture()
            def freeze(value):
                result = original(value)
                f.stop(mode)
                return result
            with f.installed(), mock.patch.object(factory, "_freeze", side_effect=freeze):
                self.assert_closed("click")
            self.assertEqual(f.clock_calls, 0)
            self.assertEqual(len(f.calls), 1)

    def test_each_provider_checkpoint_stops_observation_and_later_work(self):
        # Exercise every provider-level check, including both sides of creation.
        original = factory._OfflineProvider.valid
        f = Fixture()
        with mock.patch.object(factory._OfflineProvider, "valid", autospec=True, side_effect=original) as spy:
            self.assertIsNotNone(f.life.observe(IDS[0]))
            count = spy.call_count
        self.assertGreaterEqual(count, 7)
        for mode in ("revoke", "expire"):
            for position in range(1, count + 1):
                f = Fixture()
                calls = [0]
                def valid(provider):
                    calls[0] += 1
                    if calls[0] == position:
                        f.stop(mode)
                    return original(provider)
                with f.installed(), mock.patch.object(factory._OfflineProvider, "valid", autospec=True, side_effect=valid):
                    self.assert_closed("click")
                before = len(f.calls)
                self.assertIsNone(f.life.observe(IDS[1]))
                self.assertEqual(len(f.calls), before)

    def test_final_click_route_and_html_checks_reject_stop_during_construction(self):
        for mode in ("revoke", "expire"):
            for entry in ("click", "route", "render"):
                f = Fixture()
                module, name = ((click, "ClickDecision") if entry == "click" else
                                (route, "IntegrationReceipt") if entry == "route" else
                                (render, "CandidateResult"))
                original = getattr(module, name)
                def construct(*args, **kwargs):
                    value = original(*args, **kwargs)
                    if entry == "render" or value.status in (click.ALLOWED, route.READY):
                        f.stop(mode)
                    return value
                with self.subTest(mode=mode, entry=entry), f.installed(), mock.patch.object(module, name, side_effect=construct):
                    self.assert_closed(entry)
                before = len(f.calls)
                self.assertIsNone(f.life.records(f.life.context))
                self.assertEqual(len(f.calls), before)

    def test_clock_regression_between_calls_and_expiry_recovery_are_terminal(self):
        for invalid in (1, 10):
            f = Fixture()
            f.time = 2
            self.assertIsNotNone(f.life.observe(IDS[0]))
            f.time = invalid
            self.assertIsNone(f.life.observe(IDS[1]))
            f.time = 3
            with f.installed():
                for entry in ("click", "route", "render"):
                    self.assert_closed(entry)
            self.assertEqual(len(f.calls), 1)

    def test_invalid_monotonic_and_deadline_inputs_block_at_build(self):
        for bad in (True, False, None, "1", float("nan"), float("inf"), -float("inf")):
            self.assertIsNone(Fixture(deadline=bad).life)
            self.assertIsNone(Fixture(monotonic_clock=lambda: bad).life)

    def test_runtime_clock_invalidity_is_terminal(self):
        for bad in (True, None, "1", float("nan"), float("inf"), -float("inf")):
            f = Fixture()
            f.time = bad
            with f.installed():
                self.assert_closed("click")
                f.time = 0
                self.assert_closed("route")
            self.assertEqual(f.calls, [])

    def test_revocation_is_irreversible_and_new_lifecycle_is_separate(self):
        old, new = Fixture(), Fixture()
        old.life.revoke()
        old.life.revoke()
        for name in ("_active", "_generation", "_terminal_generation", "generation"):
            with self.assertRaises(AttributeError):
                setattr(old.life.lease, name, True)
        self.assertIsNot(old.life.lease, new.life.lease)
        self.assertIsNot(old.life.generation, new.life.generation)
        with old.installed():
            self.assert_closed("click")
        with new.installed():
            self.assertEqual(public_click().status, click.ALLOWED)

    def test_cached_observation_and_all_binding_mismatches_are_rejected(self):
        old, new = Fixture(), Fixture()
        cached = old.life.observe(IDS[0])
        old.life.revoke()
        variants = (
            cached, replace(cached, lease=new.life.lease),
            replace(cached, generation=new.life.generation),
            replace(cached, context=new.life.context),
            replace(cached, provider=new.life.provider),
        )
        for item in variants:
            with new.installed(), mock.patch.object(composition._OfflineComposition, "observe", return_value=item):
                self.assert_closed("click")
                self.assert_closed("route")
        variants = (
            replace(new.life, context=old.life.context),
            replace(new.life, provider=old.life.provider),
            replace(new.life, lease=old.life.lease),
            replace(new.life, generation=object()),
            replace(new.life, context=replace(new.life.context)),
            replace(new.life, provider=replace(new.life.provider)),
        )
        for value in variants:
            with mock.patch.object(composition, "production_provider", return_value=value):
                for entry in ("click", "route", "render"):
                    self.assert_closed(entry)
        self.assertEqual(new.calls, [])

    def test_render_rejects_cached_records_after_revoke(self):
        old, new = Fixture(), Fixture()
        records = old.life.records(old.life.context)
        old.life.revoke()
        with new.installed(), mock.patch.object(composition._OfflineComposition, "records", return_value=records):
            self.assert_closed("render")
        self.assertEqual(new.calls, [])

    def test_default_and_public_injection_stay_closed(self):
        for entry in ("click", "route", "render"):
            self.assert_closed(entry)
        for target, values in ((click.decide, dict(version=click.VERSION, clicked_public_id=IDS[0], evaluated_at=NOW)),
                               (route.assess, route_args()), (render.render, dict(as_of=NOW))):
            for name in ("lease", "token", "generation", "state", "clock", "deadline", "provider", "transport"):
                self.assertNotIn(name, inspect.signature(target).parameters)
                with self.assertRaises(TypeError):
                    target(**values, **{name: object()})

    def test_redacted_repr_receipts_logs_and_exceptions(self):
        f = Fixture()
        observation = f.life.observe(IDS[0])
        representations = repr((f.life, f.life.provider, f.life.context, f.life.lease, observation))
        for value in (IDS[0], TARGET, "content-0", "generation=", "deadline=", "0x"):
            self.assertNotIn(value, representations)
        stdout, stderr = io.StringIO(), io.StringIO()
        marker = "private-exception-marker"
        def failure():
            raise RuntimeError(marker)
        f.on_transport = failure
        with redirect_stdout(stdout), redirect_stderr(stderr), f.installed():
            receipt = public_click()
            try:
                render.render(as_of=NOW)
            except ValueError:
                error = traceback.format_exc()
        text = str(receipt.to_dict()) + stdout.getvalue() + stderr.getvalue() + error
        for value in (marker, IDS[0], TARGET, "content-0"):
            self.assertNotIn(value, text)

    def test_freshness_boundary_and_pr_rel_escape_regressions(self):
        for age, expected in ((timedelta(minutes=15), click.ALLOWED),
                              (timedelta(minutes=15, microseconds=1), click.BLOCKED),
                              (timedelta(seconds=-1), click.BLOCKED)):
            f = Fixture()
            f.wall_time = NOW - age
            with f.installed():
                self.assertEqual(public_click().status, expected)
        f = Fixture()
        records = f.life.records(f.life.context)
        records = tuple(replace(item, title='<script>"fixture"</script>') for item in records)
        with f.installed(), mock.patch.object(composition._OfflineComposition, "records", return_value=records):
            result = render.render(as_of=NOW)
        self.assertIn("&lt;script&gt;", result.html)
        self.assertIn('rel="noopener noreferrer sponsored"', result.html)
        self.assertEqual(result.html.count("PR："), 10)
        self.assertNotIn(TARGET, result.html)


if __name__ == "__main__":
    unittest.main()
