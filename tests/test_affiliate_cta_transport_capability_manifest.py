from pathlib import Path
import inspect
from decimal import Decimal
from fractions import Fraction
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_bounded_send_contract as bounded
import affiliate_cta_canary_offline_candidate as render
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_pretransport_safety as safety
import affiliate_cta_production_composition as composition
import affiliate_cta_runtime_inert_integration as route
import affiliate_cta_transport_capability_manifest as subject


def manifest(**changes):
    values = dict(
        contract_version=subject.CONTRACT_VERSION,
        official_wire_contract_version=subject.UNCONFIRMED,
        bounded_timeout=True, cancel_capability=True, no_retry=True, sequential=True,
        max_items=subject.MAX_SEQUENTIAL_ITEMS, redaction=True, kill_revoke_checkpoints=True,
        late_result_discard=True,
    )
    values.update(changes)
    return subject.RealTransportCapabilityManifest(**values)


def clock(**changes):
    values = dict(monotonic=True, unit=subject.CLOCK_UNIT, finite_range=True,
                  nondecreasing=True, process_local_limitation_acknowledged=True)
    values.update(changes)
    return subject.ClockAdapterContract(**values)


def runbook(**changes):
    values = dict(default_disabled=True, revoke_procedure=True, rollback_procedure=True,
                  audit_reason=True, reenable_requires_new_approval=True, automatic_unlock=False)
    values.update(changes)
    return subject.KillOperationsRunbookContract(**values)


def assess(**changes):
    values = dict(manifest=manifest(), setting_names=tuple(sorted(safety.REQUIRED_SETTING_NAMES)),
                  clock_contract=clock(), kill_runbook=runbook())
    values.update(changes)
    return subject.evaluate_connection_preflight(**values)


class TransportCapabilityManifestTests(unittest.TestCase):
    def test_defaults_are_disabled_and_production_has_no_adapter(self):
        self.assertIsNone(subject.production_transport_adapter())
        self.assertIsNone(composition.production_provider())
        self.assertEqual(subject.disabled_manifest().official_wire_contract_version, subject.UNCONFIRMED)
        self.assertEqual(assess().status, subject.BLOCKED)
        self.assertIn("OFFICIAL_WIRE_CONTRACT_UNCONFIRMED", assess().reason_codes)

    def test_every_missing_false_invalid_or_extra_capability_blocks(self):
        fields = ("bounded_timeout", "cancel_capability", "no_retry", "sequential", "redaction", "kill_revoke_checkpoints", "late_result_discard")
        for field in fields:
            for bad in (False, "false", 1, object(), [True]):
                with self.subTest(field=field, bad_type=type(bad)):
                    receipt = assess(manifest=manifest(**{field: bad}))
                    self.assertEqual(receipt.reason_codes, ("TRANSPORT_CAPABILITY_INVALID",))
        for bad in (0, 9, 11, True, 10.0, Decimal(10), Fraction(10), object(), [10]):
            with self.subTest(max_items=bad):
                self.assertEqual(assess(manifest=manifest(max_items=bad)).reason_codes, ("TRANSPORT_CAPABILITY_INVALID",))
        self.assertEqual(assess(manifest=object()).status, subject.BLOCKED)

    def test_settings_schema_rejects_missing_extra_values_and_invalid_types_without_reading_values(self):
        names = tuple(sorted(safety.REQUIRED_SETTING_NAMES))
        cases = (names[:-1], names + ("EXTRA",), [*names], {"value": "not-a-name"})
        for value in cases:
            with self.subTest(value_type=type(value)):
                self.assertEqual(assess(setting_names=value).status, subject.BLOCKED)

    def test_clock_and_kill_contract_boundaries_block(self):
        for changes in ({"monotonic": False}, {"unit": "milliseconds"}, {"finite_range": False}, {"nondecreasing": False}, {"process_local_limitation_acknowledged": False}):
            with self.subTest(clock=changes):
                self.assertEqual(assess(clock_contract=clock(**changes)).status, subject.BLOCKED)
        for changes in ({"default_disabled": False}, {"revoke_procedure": False}, {"rollback_procedure": False}, {"audit_reason": False}, {"reenable_requires_new_approval": False}, {"automatic_unlock": True}):
            with self.subTest(runbook=changes):
                self.assertEqual(assess(kill_runbook=runbook(**changes)).status, subject.BLOCKED)

    def test_exact_boolean_schema_rejects_truthy_and_malicious_values(self):
        class Explodes:
            def __bool__(self): raise RuntimeError("private-marker")
            def __eq__(self, _other): raise RuntimeError("private-marker")
            def __iter__(self): raise RuntimeError("private-marker")
            def __repr__(self): return "private-marker"
        for target, constructor, field in (("manifest", manifest, "bounded_timeout"), ("clock", clock, "monotonic"), ("runbook", runbook, "audit_reason")):
            for value in ("false", 1, object(), [True], Explodes()):
                with self.subTest(target=target, value_type=type(value)):
                    input_name = {"manifest": "manifest", "clock": "clock_contract", "runbook": "kill_runbook"}[target]
                    kwargs = {input_name: constructor(**{field: value})}
                    receipt = assess(**kwargs)
                    self.assertEqual(receipt.status, subject.BLOCKED)
                    self.assertNotIn("private-marker", repr(receipt))
        for target, constructor, field in (("manifest", manifest, "contract_version"), ("clock_contract", clock, "unit")):
            receipt = assess(**{target: constructor(**{field: Explodes()})})
            self.assertEqual(receipt.status, subject.BLOCKED)
            self.assertEqual(receipt.reason_codes, ("TRANSPORT_CAPABILITY_INVALID",) if target == "manifest" else ("CLOCK_CONTRACT_INVALID",))

    def test_all_boolean_fields_reject_nonboolean_schema_values(self):
        class IntSubclass(int): pass
        values = ("false", 1, IntSubclass(1), object(), [True])
        groups = (
            ("manifest", manifest, ("bounded_timeout", "cancel_capability", "no_retry", "sequential", "redaction", "kill_revoke_checkpoints", "late_result_discard"), "TRANSPORT_CAPABILITY_INVALID"),
            ("clock_contract", clock, ("monotonic", "finite_range", "nondecreasing", "process_local_limitation_acknowledged"), "CLOCK_CONTRACT_INVALID"),
            ("kill_runbook", runbook, ("default_disabled", "revoke_procedure", "rollback_procedure", "audit_reason", "reenable_requires_new_approval"), "KILL_RUNBOOK_INVALID"),
        )
        for input_name, constructor, fields, reason in groups:
            for field in fields:
                for value in values:
                    with self.subTest(input_name=input_name, field=field, value_type=type(value)):
                        self.assertEqual(assess(**{input_name: constructor(**{field: value})}).reason_codes, (reason,))
        for value in (True, "false", 1, IntSubclass(1), object(), [False]):
            with self.subTest(automatic_unlock_type=type(value)):
                self.assertEqual(assess(kill_runbook=runbook(automatic_unlock=value)).reason_codes, ("KILL_RUNBOOK_INVALID",))

    def test_marker_and_settings_name_schema_is_exact_and_prioritized(self):
        bad_markers = (None, 1, object(), "", "bad marker", "x" * 65)
        for field in ("contract_version", "official_wire_contract_version"):
            for value in bad_markers:
                with self.subTest(field=field, value_type=type(value)):
                    self.assertEqual(assess(manifest=manifest(**{field: value})).reason_codes, ("TRANSPORT_CAPABILITY_INVALID",))
        for value in bad_markers:
            with self.subTest(unit_type=type(value)):
                self.assertEqual(assess(clock_contract=clock(unit=value)).reason_codes, ("CLOCK_CONTRACT_INVALID",))
        names = tuple(sorted(safety.REQUIRED_SETTING_NAMES))
        for value in (names[:-1], names + ("EXTRA",), tuple(name.lower() for name in names), tuple("x" * 129 for _ in names)):
            with self.subTest(settings=value):
                self.assertEqual(assess(setting_names=value).reason_codes, ("SETTINGS_SCHEMA_INVALID",))

    def test_public_boundary_returns_sanitized_schema_error_for_unexpected_input_exception(self):
        with mock.patch.object(subject, "_settings_schema_valid", side_effect=RuntimeError("private-marker")):
            receipt = assess()
        self.assertEqual(receipt.reason_codes, ("CAPABILITY_SCHEMA_INVALID",))
        self.assertNotIn("private-marker", repr(receipt))

    def test_fake_clock_conformance_is_pure_and_fail_closed(self):
        self.assertTrue(subject._fake_clock_conforms_for_test((0, 0, 1.0)))
        for values in ((), (0, float("nan")), (0, float("inf")), (1, 0), (True,), (10 ** 1000,), (Decimal(1),), (Fraction(1),)):
            with self.subTest(values=values):
                self.assertFalse(subject._fake_clock_conforms_for_test(values))

    def test_future_mocked_connection_review_stays_nonactivating(self):
        with mock.patch.object(subject, "OFFICIAL_WIRE_CONTRACT_VERSION", "confirmed-test-v1"):
            receipt = assess(manifest=manifest(official_wire_contract_version="confirmed-test-v1"))
        self.assertEqual(receipt.status, subject.READY_FOR_CONNECTION_REVIEW)
        self.assertTrue(receipt.connection_review_allowed)
        self.assertFalse(any((receipt.activation_allowed, receipt.production_write_performed, receipt.deployment_allowed, receipt.route_enabled)))
        self.assertIsNone(subject.production_transport_adapter())
        self.assertIsNone(composition.production_provider())

    def test_receipt_is_sanitized_and_all_activation_capabilities_are_false(self):
        receipt = assess()
        self.assertEqual(set(receipt.__dataclass_fields__), {"contract_version", "status", "capability_not_ready", "connection_review_allowed", "activation_allowed", "production_write_performed", "deployment_allowed", "route_enabled", "reason_codes"})
        self.assertTrue(all(value is False for value in (receipt.connection_review_allowed, receipt.activation_allowed, receipt.production_write_performed, receipt.deployment_allowed, receipt.route_enabled)))
        self.assertNotIn("endpoint", repr(manifest()).lower())
        self.assertNotIn("credential", repr(manifest()).lower())

    def test_public_entries_cannot_inject_manifest_settings_transport_clock_or_kill(self):
        forbidden = {"manifest", "settings", "transport", "clock", "kill", "executor", "timeout", "cancel", "send"}
        for entry in (click.decide, render.render, route.assess):
            with self.subTest(entry=entry.__name__):
                self.assertTrue(forbidden.isdisjoint(inspect.signature(entry).parameters))

    def test_existing_disabled_adapters_and_bounded_contract_remain_inert(self):
        self.assertIsNone(safety.DisabledSettingsAdapter().read("any"))
        self.assertIsNone(safety.DisabledTransport().request(object()))
        self.assertIsNone(bounded.production_bounded_executor())


if __name__ == "__main__":
    unittest.main()
