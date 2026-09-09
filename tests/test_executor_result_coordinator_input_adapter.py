from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import executor_result_authentication as authentication  # noqa: E402
import executor_result_coordinator_input_adapter as adapter  # noqa: E402


def authenticated(outcome=authentication.COMPLETED):
    action = {
        authentication.COMPLETED: "COMPLETE_JOB_DURABLY",
        authentication.FAILED_SAFE: "FAIL_JOB_SAFE_DURABLY",
    }[outcome]
    return authentication.ExecutorResultAuthentication(
        authentication.AUTHENTICATION_VERSION,
        "EXECUTOR_RESULT_AUTHENTICATED", True, "job-a", 2, outcome,
        action, ("EXECUTOR_RESULT_AUTHENTICATED",))


class ExecutorResultCoordinatorInputAdapterTests(unittest.TestCase):
    def test_completion_route_exact_schema(self):
        result = adapter.adapt_authenticated_executor_result(authenticated())
        self.assertEqual(result.adapter_version, "0.1")
        self.assertEqual(result.status, "COORDINATOR_INPUT_READY")
        self.assertEqual((result.route, result.operation), (
            "DURABLE_JOB_COMPLETION_COORDINATOR",
            "complete_running_job_durably"))
        self.assertEqual((result.expected_job_id,
                          result.expected_attempt_count), ("job-a", 2))
        self.assertEqual(set(result.to_dict()), {
            "adapter_version", "status", "route", "operation",
            "expected_job_id", "expected_attempt_count", "reason_codes"})

    def test_failed_safe_route(self):
        result = adapter.adapt_authenticated_executor_result(
            authenticated(authentication.FAILED_SAFE))
        self.assertEqual((result.route, result.operation), (
            "DURABLE_JOB_FAILED_SAFE_COORDINATOR", "fail_running_job_durably"))

    def test_invalid_or_modified_authentication_is_redacted_and_blocked(self):
        valid = authenticated()
        values = (
            None, {}, "fixture-secret", replace(valid, authenticated=False),
            replace(valid, job_id="secret-token"),
            replace(valid, attempt_count=True),
            replace(valid, outcome=authentication.FAILED_SAFE),
            replace(valid, next_action="FAIL_JOB_SAFE_DURABLY"),
            replace(valid, reason_codes=("OTHER",)),
        )
        for value in values:
            with self.subTest(value=value):
                result = adapter.adapt_authenticated_executor_result(value)
                self.assertEqual(result.status, "COORDINATOR_INPUT_BLOCKED")
                self.assertEqual(result.route, "NONE")
                self.assertIsNone(result.operation)
                self.assertIsNone(result.expected_job_id)
                self.assertIsNone(result.expected_attempt_count)
                self.assertNotIn("secret", repr(result).lower())

    def test_public_validator_is_reused_once(self):
        with mock.patch.object(
                authentication, "validate_executor_result_authentication",
                wraps=authentication.validate_executor_result_authentication) as validate:
            self.assertEqual(
                adapter.adapt_authenticated_executor_result(authenticated()).status,
                "COORDINATOR_INPUT_READY")
        validate.assert_called_once()

    def test_exception_fails_closed_without_details(self):
        with mock.patch.object(
                authentication, "validate_executor_result_authentication",
                side_effect=RuntimeError("fixture-secret")):
            result = adapter.adapt_authenticated_executor_result(authenticated())
        self.assertEqual(result.reason_codes, ("INTERNAL_ADAPTER_ERROR",))
        self.assertNotIn("fixture-secret", repr(result))

    def test_result_is_frozen(self):
        result = adapter.adapt_authenticated_executor_result(authenticated())
        with self.assertRaises(FrozenInstanceError):
            result.route = "NONE"

    def test_ready_result_validator_rejects_modified_values(self):
        valid = adapter.adapt_authenticated_executor_result(authenticated())
        self.assertTrue(adapter.validate_coordinator_input(valid))
        for value in (
            None, {}, replace(valid, operation="fail_running_job_durably"),
            replace(valid, expected_job_id="secret-token"),
            replace(valid, expected_attempt_count=True),
            replace(valid, reason_codes=("OTHER",)),
        ):
            self.assertFalse(adapter.validate_coordinator_input(value))

    def test_source_has_no_effect_or_coordinator_imports(self):
        source = Path(adapter.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "durable_job_completion_coordinator",
            "durable_job_failed_safe_coordinator", "subprocess", "save_queue(",
            "load_queue(", "execute(", "send_notification", "checkpoint",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
