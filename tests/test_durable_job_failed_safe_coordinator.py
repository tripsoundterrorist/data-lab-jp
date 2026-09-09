import ast
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import durable_job_failed_safe_coordinator as coordinator  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


def snapshot(*jobs, revision=0):
    return persistence.PersistedQueueSnapshot(
        core.get_queue_identity(), revision, tuple(jobs), ())


class DurableJobFailedSafeCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = persistence.QueuePersistenceStore.for_test(
            Path(self.temp.name).resolve())

    def running(self, job_id="job-a", attempt_count=1):
        return job(job_id, state=core.RUNNING, attempt_count=attempt_count)

    def initialize(self, *jobs):
        self.assertEqual(self.store.initialize_for_test(snapshot(*jobs)).status, "SAVED")

    def fail(self, expected_job_id="job-a", expected_attempt_count=1):
        return coordinator.fail_running_job_durably(
            self.store, expected_job_id=expected_job_id,
            expected_attempt_count=expected_attempt_count)

    def test_exact_success_and_preservation(self):
        first, other = self.running(), job("job-b", priority="P2")
        self.initialize(first, other)
        result = self.fail()
        stored = self.store.load_queue().snapshot
        self.assertEqual(result.status, "JOB_FAILED_SAFE_DURABLY")
        self.assertEqual(result.reason_codes, ("JOB_FAILED_SAFE_DURABLE",))
        self.assertTrue(result.durable)
        self.assertEqual((result.job_id, result.attempt_count, result.revision),
                         ("job-a", 1, 1))
        self.assertEqual(stored.jobs[0], replace(first, state=core.FAILED_SAFE))
        self.assertEqual(stored.jobs[1], other)

    def test_invalid_generation_rejects_before_load(self):
        for value in (None, True, 0, -1, "1"):
            with self.subTest(value=value), mock.patch.object(
                    self.store, "load_queue") as load:
                result = self.fail(expected_attempt_count=value)
            self.assertEqual(result.reason_codes, ("EXECUTION_GENERATION_INVALID",))
            load.assert_not_called()

    def test_generation_mismatch_never_calls_core_or_save(self):
        self.initialize(self.running(attempt_count=2))
        with mock.patch.object(core, "fail_job_safe") as fail, mock.patch.object(
                self.store, "save_queue") as save:
            result = self.fail()
        self.assertEqual(result.reason_codes, ("EXECUTION_GENERATION_MISMATCH",))
        fail.assert_not_called()
        save.assert_not_called()

    def test_non_running_and_unknown_job_reject(self):
        self.initialize(job(attempt_count=1))
        self.assertEqual(self.fail().reason_codes,
                         ("FAILED_SAFE_TRANSITION_INVALID",))
        with tempfile.TemporaryDirectory() as path:
            store = persistence.QueuePersistenceStore.for_test(Path(path).resolve())
            store.initialize_for_test(snapshot(self.running("other")))
            result = coordinator.fail_running_job_durably(
                store, expected_job_id="job-a", expected_attempt_count=1)
        self.assertEqual(result.reason_codes, ("JOB_IDENTITY_NOT_CURRENT",))

    def test_load_failure_never_calls_core_or_save(self):
        blocked = persistence.QueueLoadResult("0.1", "LOCKED", None, ("QUEUE_LOCKED",))
        with mock.patch.object(self.store, "load_queue", return_value=blocked), \
             mock.patch.object(core, "fail_job_safe") as fail, \
             mock.patch.object(self.store, "save_queue") as save:
            result = self.fail()
        self.assertEqual(result.reason_codes, ("QUEUE_LOCKED",))
        fail.assert_not_called()
        save.assert_not_called()

    def test_stale_cas_is_not_retried(self):
        self.initialize(self.running())
        stale = persistence.QueueSaveResult(
            "0.1", "STALE_REVISION", None, ("STALE_REVISION",))
        with mock.patch.object(self.store, "save_queue", return_value=stale) as save:
            result = self.fail()
        self.assertEqual(result.status, "FAILED_SAFE_CONFLICT")
        self.assertFalse(result.durable)
        save.assert_called_once()

    def test_uncertain_save_has_no_retry_rollback_or_second_load(self):
        self.initialize(self.running())
        uncertain = persistence.QueueSaveResult(
            "0.1", "RECOVERY_BLOCKED", None, ("QUEUE_READ_BACK_FAILED",))
        with mock.patch.object(self.store, "save_queue", return_value=uncertain) as save, \
             mock.patch.object(self.store, "load_queue",
                               wraps=self.store.load_queue) as load:
            result = self.fail()
        self.assertEqual(result.status, "JOB_FAILED_SAFE_UNCERTAIN")
        self.assertEqual(result.reason_codes, ("RECOVERY_BLOCKED",))
        self.assertFalse(result.durable)
        save.assert_called_once()
        load.assert_called_once_with()

    def test_success_uses_no_second_load(self):
        self.initialize(self.running())
        with mock.patch.object(self.store, "load_queue",
                               wraps=self.store.load_queue) as load:
            self.assertTrue(self.fail().durable)
        load.assert_called_once_with()

    def test_invalid_core_transition_never_saves(self):
        self.initialize(self.running())
        candidate, transition = core.fail_job_safe(
            self.running(), expected_job_id="job-a")
        with mock.patch.object(core, "validate_job_transition_result",
                               return_value=core.TransitionValidationResult(
                                   "0.1", False, "UNSUPPORTED", "INVALID")), \
             mock.patch.object(core, "fail_job_safe",
                               return_value=(candidate, transition)), \
             mock.patch.object(self.store, "save_queue") as save:
            result = self.fail()
        self.assertEqual(result.reason_codes, ("FAILED_SAFE_TRANSITION_INVALID",))
        save.assert_not_called()

    def test_no_execution_notification_or_production_capability(self):
        tree = ast.parse(Path(coordinator.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse(imports & {"subprocess", "os", "time"})
        self.assertFalse(calls & {"Popen", "run", "system", "spawn", "sleep",
                                  "create_event", "process_notification"})

    def test_internal_exception_is_secret_safe(self):
        self.initialize(self.running())
        with mock.patch.object(core, "fail_job_safe",
                               side_effect=ValueError("fixture-secret")):
            result = self.fail()
        self.assertEqual(result.reason_codes, ("COORDINATOR_INTERNAL_ERROR",))
        self.assertFalse(result.durable)
        self.assertNotIn("fixture-secret", repr(result))


if __name__ == "__main__":
    unittest.main()
