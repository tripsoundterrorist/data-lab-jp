import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_storage_inspection_result_contract as contract  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402


def result(**changes):
    value = persistence.ProductionStorageInspectionResult(
        "0.1", "0.1", "HEALTHY", "MISSING_EMPTY_STORAGE_ALLOWED",
        True, False, 0, 0, (), 0, 0, 0, None, 0, 0, 0, 0,
        "ABSENT", "ABSENT", "NONE",
        ("CHECKPOINT_STORAGE_ABSENT", "QUEUE_LOADED"),
    )
    return replace(value, **changes)


def missing(**changes):
    value = persistence.ProductionStorageInspectionResult(
        "0.1", None, "MISSING_REQUIRES_BOOTSTRAP",
        "MISSING_EMPTY_STORAGE_ALLOWED", False, False, None, None, (), None,
        0, 0, None, 0, 0, 0, 0, "ABSENT", "ABSENT", "NONE",
        ("CHECKPOINT_STORAGE_ABSENT", "QUEUE_FILE_MISSING"),
    )
    return replace(value, **changes)


class QueueStorageInspectionResultContractTests(unittest.TestCase):
    def test_healthy_result_is_allowed_but_not_executable(self):
        actual = contract.validate_result(result())
        self.assertEqual(actual.contract_version, "0.1")
        self.assertEqual(actual.status, "INSPECTION_RESULT_ACCEPTED")
        self.assertTrue(actual.result_valid)
        self.assertFalse(actual.execution_allowed)
        self.assertEqual(actual.output_code, "HEALTHY")
        self.assertEqual(actual.reason_codes, ("INSPECTION_OUTPUT_ALLOWED",))

    def test_every_schema_output_code_has_a_valid_shape(self):
        fixtures = (
            result(),
            missing(),
            missing(
                status="LOCKED", lock_status="PRESENT",
                action_required="OPERATOR_REVIEW",
                reason_codes=("CHECKPOINT_STORAGE_ABSENT", "QUEUE_LOCKED")),
            missing(
                status="MANUAL_REVIEW_REQUIRED", temp_status="PRESENT",
                action_required="OPERATOR_REVIEW",
                reason_codes=("CHECKPOINT_STORAGE_ABSENT",
                              "QUEUE_TEMP_ARTIFACT_PRESENT")),
            persistence.ProductionStorageInspectionResult(
                "0.1", None, "RECOVERY_BLOCKED", "RECOVERY_BLOCKED",
                False, False, None, None, (), None, None, None, None,
                None, None, None, None, "UNKNOWN", "UNKNOWN",
                "STOP_QUEUE_RECOVERY", ("PRODUCTION_QUEUE_INSPECTION_FAILED",)),
        )
        self.assertEqual(
            {contract.validate_result(value).output_code for value in fixtures},
            {"HEALTHY", "LOCKED", "MANUAL_REVIEW_REQUIRED",
             "MISSING_REQUIRES_BOOTSTRAP", "RECOVERY_BLOCKED"})

    def test_unknown_output_code_fails_closed_without_echo(self):
        actual = contract.validate_result(result(status="RAW_OUTPUT"))
        self.assertFalse(actual.result_valid)
        self.assertFalse(actual.execution_allowed)
        self.assertIsNone(actual.output_code)
        self.assertIn("OUTPUT_CODE_NOT_ALLOWED", actual.reason_codes)
        self.assertNotIn("RAW_OUTPUT", repr(actual))

    def test_exact_result_type_and_version_are_required(self):
        for value in (None, {}, result(result_version="9.9")):
            with self.subTest(value=value):
                actual = contract.validate_result(value)
                self.assertFalse(actual.result_valid)
                self.assertFalse(actual.execution_allowed)

    def test_boolean_and_count_types_are_exact(self):
        cases = (
            result(queue_exists=1),
            result(job_count=True),
            result(revision=-1),
            result(checkpoint_object_count=-1),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn(
                    "RESULT_FIELDS_INVALID",
                    contract.validate_result(value).reason_codes)

    def test_state_counts_are_bounded_to_core_states_and_total(self):
        cases = (
            result(job_count=1, state_counts=(("READY", 2),)),
            result(job_count=1, state_counts=(("UNKNOWN", 1),)),
            result(job_count=2, state_counts=(("READY", 1), ("READY", 1))),
            result(job_count=2, state_counts=(("RUNNING", 1), ("READY", 1))),
            result(job_count=1, state_counts=(([], 1),)),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn(
                    "RESULT_FIELDS_INVALID",
                    contract.validate_result(value).reason_codes)

    def test_aggregate_count_relationships_are_enforced(self):
        cases = (
            result(job_count=0, active_reference_count=1),
            result(checkpoint_object_count=1, unreferenced_object_count=1,
                   corrupt_unreferenced_count=1),
            result(active_reference_count=1, missing_reference_count=1,
                   mismatched_reference_count=1),
            result(confirmed_orphan_count=0),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn(
                    "RESULT_FIELDS_INVALID",
                    contract.validate_result(value).reason_codes)

    def test_reason_codes_are_fixed_safe_tokens(self):
        cases = (
            result(reason_codes=()),
            result(reason_codes=("QUEUE_LOADED", "QUEUE_LOADED")),
            result(reason_codes=("queue_loaded",)),
            result(reason_codes=("RAW/PATH",)),
            result(reason_codes=([],)),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn(
                    "RESULT_FIELDS_INVALID",
                    contract.validate_result(value).reason_codes)

    def test_status_semantics_reject_contradictions(self):
        cases = (
            result(action_required="OPERATOR_REVIEW"),
            result(lock_status="PRESENT"),
            missing(queue_exists=True),
            missing(status="LOCKED", action_required="OPERATOR_REVIEW"),
            missing(status="RECOVERY_BLOCKED", action_required="NONE"),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn(
                    "RESULT_SEMANTICS_INVALID",
                    contract.validate_result(value).reason_codes)

    def test_persistence_metadata_is_all_or_absent(self):
        cases = (
            result(persistence_version=None),
            missing(revision=0),
            missing(persistence_version="9.9", revision=0, job_count=0,
                    active_reference_count=0),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn(
                    "RESULT_FIELDS_INVALID",
                    contract.validate_result(value).reason_codes)

    def test_validation_result_is_frozen(self):
        actual = contract.validate_result(result())
        with self.assertRaises(FrozenInstanceError):
            actual.execution_allowed = True

    def test_contract_has_no_inspection_io_or_runtime_capability(self):
        tree = ast.parse(Path(contract.__file__).read_text(encoding="utf-8"))
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
            "subprocess", "os", "pathlib", "sqlite3", "json"})
        self.assertFalse(calls & {
            "open", "Popen", "run", "system", "save_queue",
            "load_production_queue_read_only",
            "inspect_production_queue_storage", "process_notification",
            "sleep"})


if __name__ == "__main__":
    unittest.main()
