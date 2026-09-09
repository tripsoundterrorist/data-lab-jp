from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import durable_job_completion_coordinator as completion  # noqa: E402
import durable_job_failed_safe_coordinator as failed_safe  # noqa: E402
import executor_result_coordinator_input_adapter as adapter  # noqa: E402
import executor_result_dry_composition as composition  # noqa: E402


def coordinator_input(failed=False):
    return adapter.CoordinatorInput(
        adapter.ADAPTER_VERSION, "COORDINATOR_INPUT_READY",
        ("DURABLE_JOB_FAILED_SAFE_COORDINATOR" if failed
         else "DURABLE_JOB_COMPLETION_COORDINATOR"),
        ("fail_running_job_durably" if failed
         else "complete_running_job_durably"),
        "job-a", 2, ("COORDINATOR_INPUT_READY",))


class ExecutorResultDryCompositionTests(unittest.TestCase):
    def test_completion_exact_identity_selected_but_invocation_forbidden(self):
        result = composition.compose_dry(
            coordinator_input(),
            coordinator_callable=completion.complete_running_job_durably)
        self.assertEqual(result.composition_version, "0.1")
        self.assertEqual(result.status, "DRY_COMPOSITION_READY")
        self.assertEqual((result.selected_route, result.selected_operation), (
            "DURABLE_JOB_COMPLETION_COORDINATOR",
            "complete_running_job_durably"))
        self.assertTrue(result.callable_identity_validated)
        self.assertFalse(result.invocation_allowed)
        self.assertEqual((result.expected_job_id,
                          result.expected_attempt_count), ("job-a", 2))

    def test_failed_safe_exact_identity_selected(self):
        result = composition.compose_dry(
            coordinator_input(True),
            coordinator_callable=failed_safe.fail_running_job_durably)
        self.assertEqual(result.status, "DRY_COMPOSITION_READY")
        self.assertEqual(result.selected_route,
                         "DURABLE_JOB_FAILED_SAFE_COORDINATOR")
        self.assertFalse(result.invocation_allowed)

    def test_cross_route_and_nonidentical_callables_block(self):
        def same_name(*args, **kwargs):
            raise AssertionError("must not run")

        values = (
            failed_safe.fail_running_job_durably, same_name,
            mock.Mock(name="complete_running_job_durably"), None, object(),
        )
        for value in values:
            with self.subTest(value=value):
                result = composition.compose_dry(
                    coordinator_input(), coordinator_callable=value)
                self.assertEqual(result.reason_codes,
                                 ("COORDINATOR_CALLABLE_NOT_ALLOWLISTED",))
                self.assertEqual(result.selected_route, "NONE")
                self.assertFalse(result.callable_identity_validated)
                self.assertFalse(result.invocation_allowed)

    def test_callable_is_never_invoked(self):
        injected = mock.Mock(name="allowlisted-fixture")
        key = ("DURABLE_JOB_COMPLETION_COORDINATOR",
               "complete_running_job_durably")
        with mock.patch.dict(composition._ALLOWLIST, {key: injected}):
            result = composition.compose_dry(
                coordinator_input(), coordinator_callable=injected)
        self.assertEqual(result.status, "DRY_COMPOSITION_READY")
        injected.assert_not_called()

    def test_invalid_input_is_revalidated_and_redacted(self):
        valid = coordinator_input()
        values = (
            None, {}, "fixture-secret",
            replace(valid, operation="fail_running_job_durably"),
            replace(valid, expected_job_id="secret-token"),
            replace(valid, expected_attempt_count=True),
        )
        for value in values:
            with self.subTest(value=value):
                result = composition.compose_dry(
                    value, coordinator_callable=completion.complete_running_job_durably)
                self.assertEqual(result.reason_codes,
                                 ("COORDINATOR_INPUT_INVALID",))
                self.assertIsNone(result.expected_job_id)
                self.assertNotIn("secret", repr(result).lower())

    def test_output_exact_schema_frozen_and_contains_no_callable(self):
        result = composition.compose_dry(
            coordinator_input(),
            coordinator_callable=completion.complete_running_job_durably)
        self.assertEqual(set(result.to_dict()), {
            "composition_version", "status", "selected_route",
            "selected_operation", "callable_identity_validated",
            "expected_job_id", "expected_attempt_count", "invocation_allowed",
            "reason_codes"})
        self.assertNotIn("function", repr(result).lower())
        with self.assertRaises(FrozenInstanceError):
            result.invocation_allowed = True

    def test_internal_exception_is_safe(self):
        with mock.patch.object(
                composition.adapter, "validate_coordinator_input",
                side_effect=RuntimeError("fixture-secret")):
            result = composition.compose_dry(
                coordinator_input(),
                coordinator_callable=completion.complete_running_job_durably)
        self.assertEqual(result.reason_codes, ("INTERNAL_COMPOSITION_ERROR",))
        self.assertNotIn("fixture-secret", repr(result))

    def test_api_and_source_have_no_store_or_invocation_surface(self):
        source = Path(composition.__file__).read_text(encoding="utf-8")
        self.assertNotIn("store", composition.compose_dry.__annotations__)
        for forbidden in ("save_queue(", "load_queue(", "subprocess",
                          "send_notification", "checkpoint", "coordinator_callable("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
