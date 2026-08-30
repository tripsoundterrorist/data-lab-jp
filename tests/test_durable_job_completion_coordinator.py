import ast
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import durable_job_completion_coordinator as coordinator  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


def snapshot(*jobs, revision=0):
    return persistence.PersistedQueueSnapshot(
        core.get_queue_identity(), revision, tuple(jobs), ())


class DurableJobCompletionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = persistence.QueuePersistenceStore.for_test(
            Path(self.temp.name).resolve())

    def initialize(self, *jobs):
        self.assertEqual(self.store.initialize_for_test(snapshot(*jobs)).status, "SAVED")

    def complete(self, expected_job_id="job-a", expected_attempt_count=1):
        return coordinator.complete_running_job_durably(
            self.store, expected_job_id=expected_job_id,
            expected_attempt_count=expected_attempt_count)

    def running(self, job_id="job-a", attempt_count=1):
        return job(job_id, state=core.RUNNING, attempt_count=attempt_count)

    def test_version_and_exact_success_result(self):
        self.initialize(self.running())
        result = self.complete()
        self.assertEqual(result.coordinator_version, "0.1")
        self.assertEqual((result.status, result.job_id, result.attempt_count, result.revision),
                         ("COMPLETED", "job-a", 1, 1))
        self.assertEqual(result.reason_codes, ("JOB_COMPLETION_DURABLE",))

    def test_durable_done_and_other_jobs_preserved(self):
        first, second = self.running(), job("job-b", priority="P2")
        self.initialize(first, second)
        self.assertEqual(self.complete().status, "COMPLETED")
        stored = self.store.load_queue().snapshot
        self.assertEqual(stored.jobs[0], replace(first, state=core.DONE))
        self.assertEqual(stored.jobs[1], second)

    def test_generation_mismatch_does_not_call_core_or_write(self):
        self.initialize(self.running(attempt_count=2))
        before = self.store.queue_path.read_bytes()
        with mock.patch.object(core, "complete_job") as complete, \
             mock.patch.object(self.store, "save_queue") as save:
            result = self.complete(expected_attempt_count=1)
        self.assertEqual(result.reason_codes, ("EXECUTION_GENERATION_MISMATCH",))
        complete.assert_not_called()
        save.assert_not_called()
        self.assertEqual(self.store.queue_path.read_bytes(), before)

    def test_invalid_generation_rejected_before_load(self):
        for value in (None, True, 0, -1, "1"):
            with self.subTest(value=value), mock.patch.object(self.store, "load_queue") as load:
                result = self.complete(expected_attempt_count=value)
            self.assertEqual(result.reason_codes, ("EXECUTION_GENERATION_INVALID",))
            load.assert_not_called()

    def test_non_running_core_rejection_does_not_write(self):
        self.initialize(job(attempt_count=1))
        before = self.store.queue_path.read_bytes()
        result = self.complete()
        self.assertEqual(result.status, "COMPLETION_REJECTED")
        self.assertEqual(result.reason_codes, ("COMPLETION_TRANSITION_INVALID",))
        self.assertEqual(self.store.queue_path.read_bytes(), before)

    def test_unknown_job_rejected(self):
        self.initialize(self.running("other"))
        self.assertEqual(self.complete().reason_codes, ("JOB_IDENTITY_NOT_CURRENT",))

    def test_load_failure_does_not_call_core_or_save(self):
        blocked = persistence.QueueLoadResult("0.1", "LOCKED", None, ("QUEUE_LOCKED",))
        with mock.patch.object(self.store, "load_queue", return_value=blocked), \
             mock.patch.object(core, "complete_job") as complete, \
             mock.patch.object(self.store, "save_queue") as save:
            result = self.complete()
        self.assertEqual(result.reason_codes, ("QUEUE_LOCKED",))
        complete.assert_not_called()
        save.assert_not_called()

    def test_stale_cas_is_not_retried(self):
        self.initialize(self.running())
        stale = persistence.QueueSaveResult("0.1", "STALE_REVISION", None,
                                            ("STALE_REVISION",))
        with mock.patch.object(self.store, "save_queue", return_value=stale) as save:
            result = self.complete()
        self.assertEqual(result.status, "PERSISTENCE_NOT_CONFIRMED")
        self.assertEqual(result.reason_codes, ("STALE_REVISION",))
        save.assert_called_once()

    def test_read_back_mismatch_fails_closed(self):
        self.initialize(self.running())
        initial = self.store.load_queue()
        mismatch = persistence.QueueLoadResult(
            "0.1", "HEALTHY", replace(initial.snapshot, revision=1), ("QUEUE_LOADED",))
        with mock.patch.object(self.store, "load_queue", side_effect=[initial, mismatch]):
            result = self.complete()
        self.assertEqual(result.reason_codes, ("QUEUE_CONFIRMATION_MISMATCH",))

    def test_no_process_or_notification_capability(self):
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

    def test_internal_exception_is_safe(self):
        self.initialize(self.running())
        with mock.patch.object(core, "complete_job",
                               side_effect=ValueError("fixture-secret")):
            result = self.complete()
        self.assertEqual(result.reason_codes, ("COORDINATOR_INTERNAL_ERROR",))
        self.assertNotIn("fixture-secret", repr(result))


if __name__ == "__main__":
    unittest.main()
