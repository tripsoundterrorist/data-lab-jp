import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import queue_input_job_payload_contract as inputs  # noqa: E402
import queue_storage_inspection_payload_schema as schema  # noqa: E402
import unattended_job_queue as core  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


def candidate_job(**changes):
    value = job(job_type=schema.JOB_TYPE, risk_class=core.READ_ONLY)
    return replace(value, **changes)


def candidate_payload(value, **changes):
    payload = inputs.JobPayloadContract(
        inputs.PAYLOAD_CONTRACT_VERSION, value.job_id, value.job_type,
        schema.PAYLOAD_MODE, ())
    return replace(payload, **changes)


class QueueStorageInspectionPayloadSchemaTests(unittest.TestCase):
    def validate(self, value=None, payload=None, contract=None):
        selected = candidate_job() if value is None else value
        return schema.validate_candidate(
            selected,
            candidate_payload(selected) if payload is None else payload,
            schema.get_schema() if contract is None else contract)

    def test_exact_schema(self):
        actual = schema.get_schema()
        self.assertEqual(actual.schema_version, "0.1")
        self.assertEqual(actual.job_type, "queue_storage_inspection")
        self.assertEqual(actual.payload_mode, "LOCAL_READ_ONLY")
        self.assertEqual(actual.provenance, "BUILTIN_POLICY")
        self.assertEqual(actual.parameter_codes, ())
        self.assertEqual(actual.preflight_codes,
                         ("PRODUCTION_WRITE_DISABLED", "QUEUE_IDENTITY_VALID"))
        self.assertEqual(actual.max_runtime_seconds, 5)
        self.assertEqual(actual.output_codes, tuple(sorted(actual.output_codes)))

    def test_valid_candidate_is_still_not_executable(self):
        result = self.validate()
        self.assertEqual(result.status, "PAYLOAD_SCHEMA_VALID")
        self.assertTrue(result.schema_valid)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.reason_codes, ("LOCAL_READ_ONLY_SCHEMA_VALID",))

    def test_schema_is_exact_not_extensible(self):
        for changed in (
            replace(schema.get_schema(), provenance="CALLER_SUPPLIED"),
            replace(schema.get_schema(), max_runtime_seconds=6),
            replace(schema.get_schema(), parameter_codes=("PATH",)),
            replace(schema.get_schema(), output_codes=("RAW_OUTPUT",)),
        ):
            with self.subTest(changed=changed):
                self.assertEqual(self.validate(contract=changed).reason_codes,
                                 ("SCHEMA_CONTRACT_INVALID",))

    def test_job_profile_is_exact(self):
        cases = (
            candidate_job(job_type="other"),
            candidate_job(risk_class=core.LOW_RISK_LOCAL),
            candidate_job(state=core.RUNNING),
            candidate_job(attempt_count=1),
            candidate_job(requires_approval=True, risk_class=core.APPROVAL_REQUIRED),
            candidate_job(dependencies=("dep",)),
            candidate_job(blocker_codes=("BLOCKED",)),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertIn("JOB_PROFILE_INVALID", self.validate(value=value).reason_codes)

    def test_payload_binding_is_exact(self):
        value = candidate_job()
        cases = (
            candidate_payload(value, job_id="other"),
            candidate_payload(value, job_type="other"),
            candidate_payload(value, payload_version="9.9"),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.validate(value=value, payload=payload).reason_codes,
                                 ("PAYLOAD_JOB_BINDING_INVALID",))

    def test_no_parameters_paths_or_commands(self):
        value = candidate_job()
        for payload in (
            candidate_payload(value, payload_mode="COMMAND"),
            candidate_payload(value, parameter_codes=("PATH",)),
            candidate_payload(value, parameter_codes=("DRY_RUN",)),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.validate(value=value, payload=payload).reason_codes,
                                 ("PAYLOAD_PARAMETERS_INVALID",))

    def test_untyped_inputs_rejected(self):
        value = candidate_job()
        self.assertEqual(schema.validate_candidate({}, candidate_payload(value), schema.get_schema()).reason_codes,
                         ("JOB_CONTRACT_INVALID",))
        self.assertEqual(schema.validate_candidate(value, {}, schema.get_schema()).reason_codes,
                         ("PAYLOAD_CONTRACT_INVALID",))
        self.assertEqual(schema.validate_candidate(value, candidate_payload(value), {}).reason_codes,
                         ("SCHEMA_CONTRACT_INVALID",))

    def test_contracts_are_frozen(self):
        actual = schema.get_schema()
        result = self.validate()
        with self.assertRaises(FrozenInstanceError):
            actual.max_runtime_seconds = 10
        with self.assertRaises(FrozenInstanceError):
            result.execution_allowed = True

    def test_no_io_persistence_execution_notification_or_scheduler(self):
        tree = ast.parse(Path(schema.__file__).read_text(encoding="utf-8"))
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
                                  "inspect_production_queue_storage", "process_notification",
                                  "sleep"})


if __name__ == "__main__":
    unittest.main()
