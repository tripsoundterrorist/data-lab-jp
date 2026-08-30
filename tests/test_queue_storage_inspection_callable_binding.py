import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_storage_inspection_callable_binding as binding  # noqa: E402
import unattended_job_queue as core  # noqa: E402


class QueueStorageInspectionCallableBindingTests(unittest.TestCase):
    def test_exact_binding_is_pinned_but_preflight_remains_pending(self):
        actual = binding.validate_binding(
            binding.get_binding(), core.get_queue_identity())
        self.assertEqual(actual.binding_version, "0.1")
        self.assertEqual(actual.status, "CALLABLE_BOUND_PREFLIGHT_PENDING")
        self.assertTrue(actual.binding_valid)
        self.assertTrue(actual.identity_preflight_valid)
        self.assertFalse(actual.production_write_preflight_valid)
        self.assertTrue(actual.runtime_preflight_required)
        self.assertFalse(actual.invocation_allowed)
        self.assertFalse(actual.production_write_allowed)
        self.assertEqual(actual.max_runtime_seconds, 5)
        self.assertEqual(actual.reason_codes, (
            "PRODUCTION_WRITE_PREFLIGHT_PENDING",
            "RUNTIME_ACTIVATION_GATE_REQUIRED",
        ))

    def test_binding_metadata_is_exact(self):
        actual = binding.get_binding()
        self.assertEqual(actual.job_type, "queue_storage_inspection")
        self.assertEqual(actual.callable_module,
                         "unattended_queue_persistence")
        self.assertEqual(actual.callable_name,
                         "inspect_production_queue_storage")
        self.assertEqual(actual.return_type,
                         "ProductionStorageInspectionResult")
        self.assertEqual(actual.provenance, "BUILTIN_POLICY")
        self.assertEqual(actual.argument_codes, ())
        self.assertEqual(actual.preflight_codes, (
            "PRODUCTION_WRITE_DISABLED", "QUEUE_IDENTITY_VALID"))
        self.assertEqual(actual.max_runtime_seconds, 5)
        self.assertEqual(actual.output_codes, (
            "HEALTHY", "LOCKED", "MANUAL_REVIEW_REQUIRED",
            "MISSING_REQUIRES_BOOTSTRAP", "RECOVERY_BLOCKED"))
        self.assertEqual(actual.required_decision_version, "0.1")
        self.assertEqual(actual.required_decision_status,
                         "EXECUTOR_ACTIVATION_BLOCKED")

    def test_binding_is_exact_not_extensible(self):
        original = binding.get_binding()
        cases = (
            replace(original, callable_name="other"),
            replace(original, callable_module="other"),
            replace(original, provenance="CALLER_SUPPLIED"),
            replace(original, argument_codes=("PATH",)),
            replace(original, max_runtime_seconds=6),
            replace(original, preflight_codes=("QUEUE_IDENTITY_VALID",)),
            replace(original, output_codes=("RAW_OUTPUT",)),
            replace(original, required_decision_status="EXECUTOR_ALLOWED"),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                actual = binding.validate_binding(
                    candidate, core.get_queue_identity())
                self.assertEqual(actual.reason_codes,
                                 ("BINDING_CONTRACT_INVALID",))
                self.assertFalse(actual.invocation_allowed)

    def test_only_approved_queue_identity_is_valid(self):
        other = replace(core.get_queue_identity(), queue_id="other")
        actual = binding.validate_binding(binding.get_binding(), other)
        self.assertTrue(actual.binding_valid)
        self.assertFalse(actual.identity_preflight_valid)
        self.assertIn("QUEUE_IDENTITY_INVALID", actual.reason_codes)
        self.assertNotIn("other", repr(actual))

    def test_untyped_inputs_fail_closed(self):
        for candidate, identity in (
            ({}, core.get_queue_identity()),
            (binding.get_binding(), {}),
            (None, None),
        ):
            with self.subTest(candidate=candidate, identity=identity):
                actual = binding.validate_binding(candidate, identity)
                self.assertEqual(actual.status, "CALLABLE_BINDING_REJECTED")
                self.assertFalse(actual.invocation_allowed)

    def test_target_symbol_is_checked_without_invocation(self):
        with patch.object(
            binding.persistence, "inspect_production_queue_storage",
            autospec=True,
        ) as target, patch.object(binding, "_BOUND_CALLABLE", target):
            actual = binding.validate_binding(
                binding.get_binding(), core.get_queue_identity())
        target.assert_not_called()
        self.assertEqual(actual.status, "CALLABLE_BOUND_PREFLIGHT_PENDING")

    def test_missing_target_fails_closed(self):
        with patch.object(
            binding.persistence, "inspect_production_queue_storage", None,
        ):
            actual = binding.validate_binding(
                binding.get_binding(), core.get_queue_identity())
        self.assertIn("CALLABLE_TARGET_UNAVAILABLE", actual.reason_codes)
        self.assertFalse(actual.binding_valid)

    def test_contract_exposes_no_callable_object_or_sensitive_field(self):
        binding_fields = {item.name for item in fields(binding.CallableBinding)}
        result_fields = {item.name for item in fields(binding.BindingValidation)}
        self.assertFalse(binding_fields & {
            "callable", "handler", "path", "command", "credential",
            "queue_identity", "queue_id"})
        self.assertFalse(result_fields & {
            "callable", "handler", "path", "queue_identity", "queue_id"})

    def test_contracts_are_frozen(self):
        candidate = binding.get_binding()
        actual = binding.validate_binding(candidate, core.get_queue_identity())
        with self.assertRaises(FrozenInstanceError):
            candidate.callable_name = "other"
        with self.assertRaises(FrozenInstanceError):
            actual.invocation_allowed = True

    def test_no_io_invocation_persistence_notification_or_scheduler(self):
        tree = ast.parse(Path(binding.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse(imports & {
            "subprocess", "os", "pathlib", "sqlite3", "json", "importlib"})
        self.assertFalse(calls & {
            "open", "Popen", "run", "system", "save_queue",
            "load_production_queue_read_only",
            "inspect_production_queue_storage", "process_notification",
            "sleep", "__import__", "import_module"})


if __name__ == "__main__":
    unittest.main()
