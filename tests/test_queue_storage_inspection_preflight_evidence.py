import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_storage_inspection_callable_binding as binding  # noqa: E402
import queue_storage_inspection_preflight_evidence as evidence  # noqa: E402
import unattended_job_queue as core  # noqa: E402


def candidate(**changes):
    fixed = binding.get_binding()
    value = evidence.RuntimePreflightEvidence(
        "0.1", fixed.binding_version, fixed.callable_module,
        fixed.callable_name, "BUILTIN_RUNTIME_PREFLIGHT_CANDIDATE",
        fixed.preflight_codes, True, True, fixed.max_runtime_seconds)
    return replace(value, **changes)


class QueueStorageInspectionPreflightEvidenceTests(unittest.TestCase):
    def test_exact_candidate_remains_unattested_and_blocked(self):
        actual = evidence.validate_candidate(
            candidate(), binding.get_binding(), core.get_queue_identity())
        self.assertEqual(actual.evidence_version, "0.1")
        self.assertEqual(actual.status,
                         "RUNTIME_PREFLIGHT_EVIDENCE_UNATTESTED")
        self.assertTrue(actual.evidence_schema_valid)
        self.assertTrue(actual.binding_valid)
        self.assertTrue(actual.identity_valid)
        self.assertFalse(actual.evidence_attested)
        self.assertFalse(actual.activation_allowed)
        self.assertFalse(actual.invocation_allowed)
        self.assertEqual(actual.reason_codes,
                         ("TRUSTED_EVIDENCE_COLLECTOR_REQUIRED",))

    def test_caller_true_values_never_become_attestation(self):
        actual = evidence.validate_candidate(
            candidate(production_write_disabled=True, queue_identity_valid=True),
            binding.get_binding(), core.get_queue_identity())
        self.assertFalse(actual.evidence_attested)
        self.assertFalse(actual.activation_allowed)

    def test_candidate_is_exact_not_extensible(self):
        cases = (
            candidate(evidence_version="9.9"),
            candidate(callable_name="other"),
            candidate(provenance="CALLER_SUPPLIED"),
            candidate(observed_codes=("QUEUE_IDENTITY_VALID",)),
            candidate(production_write_disabled=False),
            candidate(queue_identity_valid=False),
            candidate(max_runtime_seconds=6),
        )
        for value in cases:
            with self.subTest(value=value):
                actual = evidence.validate_candidate(
                    value, binding.get_binding(), core.get_queue_identity())
                self.assertEqual(actual.reason_codes,
                                 ("EVIDENCE_CONTRACT_INVALID",))
                self.assertFalse(actual.evidence_attested)

    def test_binding_and_identity_are_revalidated(self):
        invalid_binding = replace(binding.get_binding(), callable_name="other")
        invalid_identity = replace(core.get_queue_identity(), queue_id="other")
        for bound, identity in (
            (invalid_binding, core.get_queue_identity()),
            (binding.get_binding(), invalid_identity),
        ):
            with self.subTest(bound=bound, identity=identity):
                actual = evidence.validate_candidate(
                    candidate(), bound, identity)
                self.assertIn("BINDING_PREFLIGHT_INVALID",
                              actual.reason_codes)
                self.assertFalse(actual.activation_allowed)

    def test_binding_validator_is_called_once(self):
        with patch.object(
            evidence.callable_binding, "validate_binding",
            wraps=evidence.callable_binding.validate_binding,
        ) as validate:
            evidence.validate_candidate(
                candidate(), binding.get_binding(), core.get_queue_identity())
        validate.assert_called_once()

    def test_validator_exception_fails_closed(self):
        with patch.object(
            evidence.callable_binding, "validate_binding",
            side_effect=RuntimeError("fixture"),
        ):
            actual = evidence.validate_candidate(
                candidate(), binding.get_binding(), core.get_queue_identity())
        self.assertEqual(actual.reason_codes,
                         ("EVIDENCE_VALIDATION_INTERNAL_ERROR",))
        self.assertFalse(actual.activation_allowed)

    def test_no_evidence_collector_or_attestation_api_exists(self):
        for name in ("collect_evidence", "attest_evidence", "activate",
                     "invoke"):
            self.assertFalse(hasattr(evidence, name))

    def test_outputs_expose_no_identity_callable_or_source_values(self):
        names = {item.name for item in fields(evidence.EvidenceValidation)}
        self.assertFalse(names & {
            "queue_identity", "queue_id", "callable", "path", "source",
            "production_write_disabled"})

    def test_contracts_are_frozen(self):
        value = candidate()
        actual = evidence.validate_candidate(
            value, binding.get_binding(), core.get_queue_identity())
        with self.assertRaises(FrozenInstanceError):
            value.production_write_disabled = False
        with self.assertRaises(FrozenInstanceError):
            actual.activation_allowed = True

    def test_no_io_collection_invocation_or_scheduler_capability(self):
        tree = ast.parse(Path(evidence.__file__).read_text(encoding="utf-8"))
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
            "sleep", "collect_evidence", "activate", "invoke"})


if __name__ == "__main__":
    unittest.main()
