import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_input_job_payload_contract as inputs  # noqa: E402
import queue_input_storage_inspection_integration as integration  # noqa: E402
import queue_storage_inspection_payload_schema as inspection  # noqa: E402
import unattended_job_queue as core  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


def inspection_job(job_id="job-1", **changes):
    value = job(
        job_id, job_type=inspection.JOB_TYPE, risk_class=core.READ_ONLY)
    return replace(value, **changes)


def payload(value, mode=None, **changes):
    actual = inputs.JobPayloadContract(
        inputs.PAYLOAD_CONTRACT_VERSION, value.job_id, value.job_type,
        inspection.PAYLOAD_MODE if mode is None else mode, ())
    return replace(actual, **changes)


def queue_input(*jobs, payloads):
    return inputs.QueueInputContract(
        inputs.INPUT_CONTRACT_VERSION, core.get_queue_identity(), tuple(jobs),
        payloads)


class QueueInputStorageInspectionIntegrationTests(unittest.TestCase):
    def test_exact_schema_is_admitted_but_not_executable(self):
        value = inspection_job()
        result = integration.validate_queue_input(
            queue_input(value, payloads=(payload(value),)))
        self.assertEqual(result.contract_version, "0.1")
        self.assertEqual(result.status, "QUEUE_INPUT_ACCEPTED")
        self.assertTrue(result.admission_allowed)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.job_count, 1)
        self.assertEqual(result.recognized_schema_count, 1)
        self.assertEqual(result.reason_codes, (
            "NON_EXECUTABLE_INPUT_VALID",
            "QUEUE_STORAGE_INSPECTION_SCHEMA_RECOGNIZED",
        ))

    def test_no_payload_input_retains_base_semantics(self):
        value = job()
        ordinary = payload(value, mode=inputs.NO_PAYLOAD)
        result = integration.validate_queue_input(
            queue_input(value, payloads=(ordinary,)))
        self.assertTrue(result.admission_allowed)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.recognized_schema_count, 0)
        self.assertEqual(result.reason_codes, ("NON_EXECUTABLE_INPUT_VALID",))

    def test_mixed_input_is_supported_without_execution(self):
        ordinary_job = job("a")
        storage_job = inspection_job("b")
        ordinary = payload(ordinary_job, mode=inputs.NO_PAYLOAD)
        result = integration.validate_queue_input(queue_input(
            ordinary_job, storage_job,
            payloads=(ordinary, payload(storage_job))))
        self.assertTrue(result.admission_allowed)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.job_count, 2)
        self.assertEqual(result.recognized_schema_count, 1)

    def test_schema_job_requires_exact_schema_payload(self):
        value = inspection_job()
        cases = (
            payload(value, mode=inputs.NO_PAYLOAD),
            payload(value, parameter_codes=("PATH",)),
            payload(value, payload_version="9.9"),
            payload(value, job_id="other"),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                result = integration.validate_queue_input(
                    queue_input(value, payloads=(candidate,)))
                self.assertFalse(result.admission_allowed)
                self.assertFalse(result.execution_allowed)
                self.assertIn(
                    "QUEUE_STORAGE_INSPECTION_SCHEMA_INVALID",
                    result.reason_codes)

    def test_exact_job_profile_is_required(self):
        cases = (
            inspection_job(risk_class=core.LOW_RISK_LOCAL),
            inspection_job(state=core.RUNNING),
            inspection_job(attempt_count=1),
            inspection_job(dependencies=("missing",)),
        )
        for value in cases:
            with self.subTest(value=value):
                result = integration.validate_queue_input(
                    queue_input(value, payloads=(payload(value),)))
                self.assertFalse(result.admission_allowed)
                self.assertIn("JOB_PROFILE_INVALID", result.reason_codes)

    def test_local_read_only_mode_cannot_extend_to_other_job_types(self):
        value = job()
        result = integration.validate_queue_input(
            queue_input(value, payloads=(payload(value),)))
        self.assertFalse(result.admission_allowed)
        self.assertIn("QUEUE_STORAGE_INSPECTION_SCHEMA_INVALID",
                      result.reason_codes)

    def test_other_payload_modes_remain_unauthorized(self):
        value = job()
        result = integration.validate_queue_input(queue_input(
            value, payloads=(payload(value, mode="PARAMETERS"),)))
        self.assertFalse(result.admission_allowed)
        self.assertIn("EXECUTABLE_PAYLOAD_NOT_AUTHORIZED",
                      result.reason_codes)

    def test_base_order_and_binding_checks_are_preserved(self):
        a, b = job("a"), inspection_job("b")
        result = integration.validate_queue_input(queue_input(
            a, b, payloads=(payload(b), payload(a, mode=inputs.NO_PAYLOAD))))
        self.assertFalse(result.admission_allowed)
        self.assertIn("PAYLOAD_ORDER_INVALID", result.reason_codes)

    def test_untyped_input_fails_closed(self):
        for value in (None, {}, [], "fixture-secret", True):
            with self.subTest(value=value):
                result = integration.validate_queue_input(value)
                self.assertEqual(result.status, "QUEUE_INPUT_REJECTED")
                self.assertFalse(result.admission_allowed)
                self.assertFalse(result.execution_allowed)

    def test_result_is_frozen(self):
        value = inspection_job()
        result = integration.validate_queue_input(
            queue_input(value, payloads=(payload(value),)))
        with self.assertRaises(FrozenInstanceError):
            result.execution_allowed = True

    def test_no_io_persistence_executor_notification_or_scheduler(self):
        tree = ast.parse(Path(integration.__file__).read_text(encoding="utf-8"))
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
            "inspect_production_queue_storage", "process_notification",
            "sleep"})


if __name__ == "__main__":
    unittest.main()
