import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_input_job_payload_contract as contract  # noqa: E402
import unattended_job_queue as core  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


def payload(value, **changes):
    base = contract.JobPayloadContract(
        contract.PAYLOAD_CONTRACT_VERSION, value.job_id, value.job_type,
        contract.NO_PAYLOAD, ())
    return replace(base, **changes)


def queue_input(*jobs, payloads=None, **changes):
    values = tuple(jobs)
    base = contract.QueueInputContract(
        contract.INPUT_CONTRACT_VERSION, core.get_queue_identity(), values,
        tuple(payload(value) for value in values) if payloads is None else payloads)
    return replace(base, **changes)


class QueueInputJobPayloadContractTests(unittest.TestCase):
    def test_version_and_valid_non_executable_input(self):
        result = contract.validate_queue_input(queue_input(job()))
        self.assertEqual(result.contract_version, "0.1")
        self.assertEqual(result.status, "QUEUE_INPUT_ACCEPTED")
        self.assertTrue(result.admission_allowed)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.job_count, 1)
        self.assertEqual(result.reason_codes, ("NON_EXECUTABLE_INPUT_VALID",))

    def test_multiple_jobs_require_sorted_payloads(self):
        a, b = job("a"), job("b")
        self.assertTrue(contract.validate_queue_input(queue_input(a, b)).admission_allowed)
        result = contract.validate_queue_input(
            queue_input(a, b, payloads=(payload(b), payload(a))))
        self.assertIn("PAYLOAD_ORDER_INVALID", result.reason_codes)

    def test_exact_one_to_one_payload_binding(self):
        a, b = job("a"), job("b")
        cases = ((payload(a),), (payload(a), payload(a)),
                 (payload(a), payload(job("other"))))
        for values in cases:
            with self.subTest(values=values):
                result = contract.validate_queue_input(queue_input(a, b, payloads=values))
                self.assertFalse(result.admission_allowed)
                self.assertIn("PAYLOAD_JOB_SET_MISMATCH", result.reason_codes)

    def test_job_type_binding_is_exact(self):
        value = job()
        result = contract.validate_queue_input(queue_input(
            value, payloads=(payload(value, job_type="other_type"),)))
        self.assertIn("PAYLOAD_JOB_BINDING_INVALID", result.reason_codes)

    def test_executable_payload_is_not_authorized(self):
        value = job()
        for changes in ({"payload_mode": "PARAMETERS"},
                        {"parameter_codes": ("DRY_RUN",)}):
            with self.subTest(changes=changes):
                result = contract.validate_queue_input(queue_input(
                    value, payloads=(payload(value, **changes),)))
                self.assertEqual(result.status, "QUEUE_INPUT_REJECTED")
                self.assertIn("EXECUTABLE_PAYLOAD_NOT_AUTHORIZED", result.reason_codes)
                self.assertFalse(result.execution_allowed)

    def test_fresh_state_is_required(self):
        for state in core.JOB_STATES - {core.READY}:
            value = job(state=state)
            if state == core.CHECKPOINTED:
                value = replace(value, checkpoint_supported=True)
            with self.subTest(state=state):
                self.assertIn("FRESH_JOB_STATE_REQUIRED",
                              contract.validate_queue_input(queue_input(value)).reason_codes)
        self.assertIn("FRESH_JOB_STATE_REQUIRED", contract.validate_queue_input(
            queue_input(job(attempt_count=1))).reason_codes)

    def test_approval_must_not_be_preapplied(self):
        value = job(requires_approval=True, risk_class=core.APPROVAL_REQUIRED)
        approved = replace(value, approval_received=True)
        result = contract.validate_queue_input(queue_input(approved))
        self.assertIn("FRESH_JOB_STATE_REQUIRED", result.reason_codes)

    def test_core_queue_validation_is_delegated(self):
        value = job()
        invalid = replace(value, dependencies=("missing",))
        result = contract.validate_queue_input(queue_input(invalid))
        self.assertIn("DEPENDENCY_UNKNOWN", result.reason_codes)

    def test_identity_validation_is_delegated(self):
        value = job()
        other = replace(core.get_queue_identity(), queue_id="other")
        result = contract.validate_queue_input(queue_input(value, queue_identity=other))
        self.assertIn("QUEUE_IDENTITY_INVALID", result.reason_codes)

    def test_empty_and_bounded_input(self):
        self.assertIn("INPUT_JOBS_INVALID",
                      contract.validate_queue_input(queue_input()).reason_codes)
        values = tuple(job(f"job-{index:03d}") for index in range(257))
        payloads = tuple(payload(value) for value in values)
        result = contract.validate_queue_input(queue_input(*values, payloads=payloads))
        self.assertIn("INPUT_JOB_LIMIT_EXCEEDED", result.reason_codes)

    def test_unknown_versions_rejected(self):
        value = job()
        self.assertIn("INPUT_VERSION_UNSUPPORTED", contract.validate_queue_input(
            queue_input(value, input_version="9.9")).reason_codes)
        self.assertIn("PAYLOAD_CONTRACT_INVALID", contract.validate_queue_input(
            queue_input(value, payloads=(payload(value, payload_version="9.9"),))).reason_codes)

    def test_untyped_and_malformed_input_rejected(self):
        for value in (None, {}, [], "fixture-secret", True):
            with self.subTest(value=value):
                result = contract.validate_queue_input(value)
                self.assertEqual(result.reason_codes, ("INPUT_CONTRACT_INVALID",))
                self.assertFalse(result.admission_allowed)
                self.assertFalse(result.execution_allowed)

    def test_forbidden_identity_words_rejected(self):
        value = job()
        for text in ("api_token", "credential", "raw_payload", "file_path"):
            with self.subTest(text=text):
                result = contract.validate_queue_input(queue_input(
                    value, payloads=(payload(value, job_type=text),)))
                self.assertIn("PAYLOAD_CONTRACT_INVALID", result.reason_codes)

    def test_results_and_contracts_are_frozen(self):
        value = job()
        input_value = queue_input(value)
        result = contract.validate_queue_input(input_value)
        with self.assertRaises(FrozenInstanceError):
            input_value.jobs = ()
        with self.assertRaises(FrozenInstanceError):
            result.execution_allowed = True

    def test_no_io_persistence_execution_or_scheduler_capability(self):
        tree = ast.parse(Path(contract.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse(imports & {"subprocess", "os", "pathlib", "sqlite3", "json"})
        self.assertFalse(calls & {"open", "Popen", "run", "system", "save_queue",
                                  "create_file", "process_notification", "sleep"})


if __name__ == "__main__":
    unittest.main()
