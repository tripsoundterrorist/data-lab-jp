from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import durable_execution_adoption_coordinator as adoption  # noqa: E402
import executor_result_authentication as authentication  # noqa: E402


def adopted(**changes):
    value = adoption.DurableExecutionAdoptionResult(
        adoption.COORDINATOR_VERSION, "EXECUTION_ADOPTED_DURABLY", True,
        "job-a", 1, 7, ("EXECUTION_ADOPTION_DURABLE",))
    return replace(value, **changes)


def evidence(**changes):
    value = authentication.ExecutorResultEvidence(
        authentication.EVIDENCE_VERSION, "job-a", 1,
        authentication.COMPLETED, "EXECUTOR_CONFIRMED_COMPLETION")
    return replace(value, **changes)


class ExecutorResultAuthenticationTests(unittest.TestCase):
    _MISSING = object()

    def authenticate(self, adoption_result=_MISSING, result_evidence=_MISSING,
                     **expected):
        return authentication.authenticate_executor_result(
            adopted() if adoption_result is self._MISSING else adoption_result,
            evidence() if result_evidence is self._MISSING else result_evidence,
            expected_job_id=expected.get("job_id", "job-a"),
            expected_attempt_count=expected.get("attempt_count", 1))

    def test_completed_exact_schema_and_action(self):
        result = self.authenticate()
        self.assertEqual(result.authentication_version, "0.1")
        self.assertEqual(result.status, "EXECUTOR_RESULT_AUTHENTICATED")
        self.assertTrue(result.authenticated)
        self.assertEqual((result.job_id, result.attempt_count, result.outcome),
                         ("job-a", 1, "COMPLETED"))
        self.assertEqual(result.next_action, "COMPLETE_JOB_DURABLY")
        self.assertEqual(set(result.to_dict()), {
            "authentication_version", "status", "authenticated", "job_id",
            "attempt_count", "outcome", "next_action", "reason_codes"})

    def test_failed_safe_exact_pair_and_action(self):
        result = self.authenticate(result_evidence=evidence(
            outcome="FAILED_SAFE", result_code="EXECUTOR_CONFIRMED_SAFE_FAILURE"))
        self.assertTrue(result.authenticated)
        self.assertEqual(result.next_action, "FAIL_JOB_SAFE_DURABLY")

    def test_outcome_and_result_code_must_be_consistent(self):
        for value in (
            evidence(outcome="FAILED_SAFE"),
            evidence(outcome="UNKNOWN", result_code="EXECUTOR_CONFIRMED_COMPLETION"),
            evidence(result_code="UNKNOWN"),
        ):
            with self.subTest(value=value):
                result = self.authenticate(result_evidence=value)
                self.assertEqual(result.reason_codes,
                                 ("EXECUTOR_RESULT_EVIDENCE_INVALID",))

    def test_expected_generation_is_strict(self):
        for job_id, count in ((None, 1), ("job-a", None), ("job-a", True),
                              ("job-a", 0), ("secret-token", 1)):
            with self.subTest(job_id=job_id, count=count):
                result = self.authenticate(job_id=job_id, attempt_count=count)
                self.assertEqual(result.reason_codes,
                                 ("EXPECTED_GENERATION_INVALID",))
                self.assertIsNone(result.job_id)

    def test_adoption_must_be_exact_durable_contract(self):
        cases = (
            None, {}, adopted(durable=False), adopted(status="ADOPTION_CONFLICT"),
            adopted(reason_codes=("OTHER",)), adopted(revision=0),
            adopted(coordinator_version="9"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = self.authenticate(adoption_result=value)
                self.assertEqual(result.reason_codes,
                                 ("ADOPTION_EVIDENCE_INVALID",))

    def test_both_inputs_bind_to_expected_generation(self):
        first = self.authenticate(adoption_result=adopted(attempt_count=2))
        second = self.authenticate(result_evidence=evidence(job_id="job-b"))
        self.assertEqual(first.reason_codes, ("ADOPTED_GENERATION_MISMATCH",))
        self.assertEqual(second.reason_codes,
                         ("EXECUTOR_RESULT_GENERATION_MISMATCH",))

    def test_unknown_missing_and_secret_bearing_evidence_rejects_without_echo(self):
        values = (
            None, {}, {"evidence_version": "0.1"},
            evidence(job_id="secret-token"), evidence(job_id="C:/private"),
        )
        for value in values:
            with self.subTest(value=value):
                result = self.authenticate(result_evidence=value)
                self.assertFalse(result.authenticated)
                self.assertEqual(result.next_action, "NONE")
                rendered = json.dumps(result.to_dict())
                for forbidden in ("secret-token", "C:/private"):
                    self.assertNotIn(forbidden, rendered)

    def test_exact_types_reject_bool_attempt_and_subclasses(self):
        class EvidenceSubclass(authentication.ExecutorResultEvidence):
            pass

        for value in (evidence(attempt_count=True), EvidenceSubclass(
                "0.1", "job-a", 1, "COMPLETED",
                "EXECUTOR_CONFIRMED_COMPLETION")):
            self.assertEqual(self.authenticate(result_evidence=value).reason_codes,
                             ("EXECUTOR_RESULT_EVIDENCE_INVALID",))

    def test_results_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.authenticate().authenticated = False
        with self.assertRaises(FrozenInstanceError):
            evidence().outcome = "FAILED_SAFE"

    def test_success_validator_rejects_modified_or_subclassed_results(self):
        valid = self.authenticate()
        self.assertTrue(
            authentication.validate_executor_result_authentication(valid))
        for value in (
            replace(valid, authenticated=False),
            replace(valid, next_action="FAIL_JOB_SAFE_DURABLY"),
            replace(valid, reason_codes=("OTHER",)),
            {}, None,
        ):
            self.assertFalse(
                authentication.validate_executor_result_authentication(value))

    def test_exception_is_fixed_and_secret_safe(self):
        with mock.patch.object(authentication, "_safe_id",
                               side_effect=RuntimeError("fixture-secret")):
            result = self.authenticate()
        self.assertEqual(result.reason_codes, ("INTERNAL_AUTHENTICATION_ERROR",))
        self.assertNotIn("fixture-secret", repr(result))

    def test_source_has_no_effect_capabilities(self):
        source = Path(authentication.__file__).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "save_queue(", "load_queue(",
                          "execute(", "send_notification", "checkpoint"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
