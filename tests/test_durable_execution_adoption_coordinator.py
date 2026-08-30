import ast
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import durable_execution_adoption_coordinator as coordinator  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402
from tests.test_unattended_job_queue import job  # noqa: E402


UTC = "2026-08-31T02:00:00Z"


def snapshot(*jobs, revision=0, refs=()):
    return persistence.PersistedQueueSnapshot(
        core.get_queue_identity(), revision, tuple(jobs), tuple(refs))


class DurableExecutionAdoptionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = persistence.QueuePersistenceStore.for_test(
            Path(self.temp.name).resolve())

    def initialize(self, *jobs, refs=()):
        result = self.store.initialize_for_test(snapshot(*jobs, refs=refs))
        self.assertEqual(result.status, "SAVED")

    def adopt(self, expected_job_id="job-a", **facts):
        return coordinator.adopt_selected_job_durably(
            self.store, expected_job_id=expected_job_id,
            occurred_at=facts.pop("occurred_at", UTC), **facts)

    def test_version_and_exact_success_result(self):
        self.initialize(job())
        result = self.adopt()
        self.assertEqual(result.coordinator_version, "0.1")
        self.assertEqual(result.status, "ADOPTED")
        self.assertEqual((result.job_id, result.attempt_count, result.revision),
                         ("job-a", 1, 1))
        self.assertEqual(result.reason_codes, ("EXECUTION_ADOPTION_DURABLE",))

    def test_durable_candidate_and_other_fields_preserved(self):
        first, second = job("job-a"), job("job-b", priority="P2")
        self.initialize(first, second)
        result = self.adopt()
        stored = self.store.load_queue().snapshot
        self.assertEqual(result.status, "ADOPTED")
        self.assertEqual(stored.jobs[0], replace(first, state=core.RUNNING, attempt_count=1))
        self.assertEqual(stored.jobs[1], second)
        self.assertEqual(stored.active_checkpoint_refs, ())

    def test_core_rejection_does_not_write(self):
        self.initialize(job(state=core.RUNNING))
        before = self.store.queue_path.read_bytes()
        result = self.adopt()
        self.assertEqual(result.status, "ADOPTION_REJECTED")
        self.assertEqual(result.reason_codes, ("EXECUTION_ADOPTION_INVALID",))
        self.assertEqual(self.store.queue_path.read_bytes(), before)

    def test_selection_change_does_not_write(self):
        self.initialize(job("old", priority="P2"), job("new", priority="P0"))
        before = self.store.queue_path.read_bytes()
        result = self.adopt(expected_job_id="old")
        self.assertEqual(result.status, "ADOPTION_REJECTED")
        self.assertEqual(result.reason_codes, ("SELECTION_CHANGED",))
        self.assertEqual(self.store.queue_path.read_bytes(), before)

    def test_invalid_store_fails_closed(self):
        result = coordinator.adopt_selected_job_durably(
            object(), expected_job_id="job-a", occurred_at=UTC)
        self.assertEqual(result.status, "RECOVERY_BLOCKED")
        self.assertEqual(result.reason_codes, ("PERSISTENCE_STORE_INVALID",))

    def test_load_failure_does_not_call_core_or_save(self):
        with mock.patch.object(self.store, "load_queue", return_value=
                persistence.QueueLoadResult("0.1", "LOCKED", None, ("QUEUE_LOCKED",))), \
             mock.patch.object(core, "adopt_ready_job_for_execution") as adopt, \
             mock.patch.object(self.store, "save_queue") as save:
            result = self.adopt()
        self.assertEqual(result.status, "RECOVERY_BLOCKED")
        self.assertEqual(result.reason_codes, ("QUEUE_LOCKED",))
        adopt.assert_not_called()
        save.assert_not_called()

    def test_stale_cas_is_not_retried(self):
        self.initialize(job())
        stale = persistence.QueueSaveResult("0.1", "STALE_REVISION", None,
                                            ("STALE_REVISION",))
        with mock.patch.object(self.store, "save_queue", return_value=stale) as save:
            result = self.adopt()
        self.assertEqual(result.status, "PERSISTENCE_NOT_CONFIRMED")
        self.assertEqual(result.reason_codes, ("STALE_REVISION",))
        save.assert_called_once()

    def test_read_back_mismatch_fails_closed(self):
        self.initialize(job())
        real_load = self.store.load_queue
        initial = real_load()
        mismatch = persistence.QueueLoadResult(
            "0.1", "HEALTHY", replace(initial.snapshot, revision=1), ("QUEUE_LOADED",))
        with mock.patch.object(self.store, "load_queue",
                               side_effect=[initial, mismatch]):
            result = self.adopt()
        self.assertEqual(result.status, "PERSISTENCE_NOT_CONFIRMED")
        self.assertEqual(result.reason_codes, ("QUEUE_CONFIRMATION_MISMATCH",))

    def test_no_executor_or_process_capability(self):
        tree = ast.parse(Path(coordinator.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse(imports & {"subprocess", "os", "time"})
        self.assertFalse(calls & {"Popen", "run", "system", "spawn", "sleep"})

    def test_internal_exception_is_safe(self):
        self.initialize(job())
        with mock.patch.object(core, "adopt_ready_job_for_execution",
                               side_effect=ValueError("fixture-secret")):
            result = self.adopt()
        self.assertEqual(result.status, "RECOVERY_BLOCKED")
        self.assertEqual(result.reason_codes, ("COORDINATOR_INTERNAL_ERROR",))
        self.assertNotIn("fixture-secret", repr(result))


if __name__ == "__main__":
    unittest.main()
