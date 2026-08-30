import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_input_job_payload_contract as inputs  # noqa: E402
import queue_storage_inspection_executor_decision as executor  # noqa: E402
import queue_storage_inspection_payload_schema as schema  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


def target_job(job_id="inspection"):
    return job(job_id, job_type=schema.JOB_TYPE, risk_class=core.READ_ONLY)


def target_payload(value):
    return inputs.JobPayloadContract(
        inputs.PAYLOAD_CONTRACT_VERSION, value.job_id, value.job_type,
        schema.PAYLOAD_MODE, ())


def queue_input(*jobs, payloads=None):
    values = tuple(jobs)
    return inputs.QueueInputContract(
        inputs.INPUT_CONTRACT_VERSION, core.get_queue_identity(), values,
        tuple(target_payload(value) for value in values)
        if payloads is None else payloads)


def healthy_result(**changes):
    value = persistence.ProductionStorageInspectionResult(
        "0.1", "0.1", "HEALTHY", "MISSING_EMPTY_STORAGE_ALLOWED",
        True, False, 0, 0, (), 0, 0, 0, None, 0, 0, 0, 0,
        "ABSENT", "ABSENT", "NONE",
        ("CHECKPOINT_STORAGE_ABSENT", "QUEUE_LOADED"),
    )
    return replace(value, **changes)


class QueueStorageInspectionExecutorDecisionTests(unittest.TestCase):
    def test_valid_boundaries_still_block_invocation(self):
        value = target_job()
        actual = executor.decide(queue_input(value), healthy_result())
        self.assertEqual(actual.decision_version, "0.1")
        self.assertEqual(actual.status, "EXECUTOR_ACTIVATION_BLOCKED")
        self.assertTrue(actual.boundaries_valid)
        self.assertFalse(actual.invocation_allowed)
        self.assertFalse(actual.production_write_allowed)
        self.assertFalse(actual.attempt_update_allowed)
        self.assertEqual(actual.max_runtime_seconds, 5)
        self.assertEqual(actual.output_code, "HEALTHY")
        self.assertEqual(
            actual.reason_codes, ("SEPARATE_ACTIVATION_GATE_REQUIRED",))

    def test_queue_input_is_revalidated_not_trusted(self):
        value = target_job()
        invalid = queue_input(
            value,
            payloads=(replace(target_payload(value), parameter_codes=("PATH",)),))
        actual = executor.decide(invalid, healthy_result())
        self.assertEqual(actual.status, "EXECUTOR_DECISION_REJECTED")
        self.assertIn("QUEUE_INPUT_NOT_ADMITTED", actual.reason_codes)
        self.assertFalse(actual.boundaries_valid)

    def test_result_is_revalidated_not_trusted(self):
        value = target_job()
        actual = executor.decide(
            queue_input(value), healthy_result(status="RAW_OUTPUT"))
        self.assertIn("INSPECTION_RESULT_NOT_ACCEPTED", actual.reason_codes)
        self.assertIsNone(actual.output_code)
        self.assertNotIn("RAW_OUTPUT", repr(actual))

    def test_target_schema_must_be_the_only_job(self):
        first, second = target_job("a"), target_job("b")
        actual = executor.decide(queue_input(first, second), healthy_result())
        self.assertIn("TARGET_SCHEMA_NOT_EXCLUSIVE", actual.reason_codes)
        self.assertFalse(actual.invocation_allowed)

    def test_ordinary_no_payload_job_cannot_reach_decision(self):
        value = job()
        ordinary = inputs.JobPayloadContract(
            inputs.PAYLOAD_CONTRACT_VERSION, value.job_id, value.job_type,
            inputs.NO_PAYLOAD, ())
        actual = executor.decide(
            queue_input(value, payloads=(ordinary,)), healthy_result())
        self.assertIn("TARGET_SCHEMA_NOT_EXCLUSIVE", actual.reason_codes)

    def test_both_invalid_boundaries_report_fixed_codes(self):
        actual = executor.decide({}, {})
        self.assertEqual(actual.reason_codes, (
            "INSPECTION_RESULT_NOT_ACCEPTED", "QUEUE_INPUT_NOT_ADMITTED"))
        self.assertFalse(actual.invocation_allowed)
        self.assertIsNone(actual.max_runtime_seconds)

    def test_boundary_validators_are_called_once(self):
        value = target_job()
        with patch.object(
            executor.queue_integration, "validate_queue_input",
            wraps=executor.queue_integration.validate_queue_input,
        ) as admission, patch.object(
            executor.result_contract, "validate_result",
            wraps=executor.result_contract.validate_result,
        ) as result_validation:
            executor.decide(queue_input(value), healthy_result())
        admission.assert_called_once()
        result_validation.assert_called_once()

    def test_boundary_exception_fails_closed(self):
        value = target_job()
        with patch.object(
            executor.queue_integration, "validate_queue_input",
            side_effect=RuntimeError("fixture"),
        ):
            actual = executor.decide(queue_input(value), healthy_result())
        self.assertEqual(
            actual.reason_codes, ("EXECUTOR_DECISION_INTERNAL_ERROR",))
        self.assertFalse(actual.invocation_allowed)

    def test_decision_contract_has_no_callable_or_source_fields(self):
        names = {item.name for item in fields(executor.ExecutorDecision)}
        self.assertFalse(names & {
            "callable", "handler", "command", "path", "credential",
            "queue_input", "inspection_result"})

    def test_decision_is_frozen(self):
        value = target_job()
        actual = executor.decide(queue_input(value), healthy_result())
        with self.assertRaises(FrozenInstanceError):
            actual.invocation_allowed = True

    def test_no_io_invocation_persistence_notification_or_scheduler(self):
        tree = ast.parse(Path(executor.__file__).read_text(encoding="utf-8"))
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
