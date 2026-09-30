from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import job_execution_adoption_coordinator as coordinator  # noqa: E402
import unattended_checkpoint_storage as checkpoints  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402
from tests.test_unattended_job_queue import checkpoint, job  # noqa: E402


UTC = "2026-08-31T02:03:04Z"


def snapshot(*jobs, revision=0, refs=()):
    return persistence.PersistedQueueSnapshot(
        core.get_queue_identity(), revision, tuple(jobs), tuple(refs))


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.checkpoints = checkpoints.CheckpointStorage.for_test(
            self.root, core.get_queue_identity())
        self.store = persistence.QueuePersistenceStore.for_test(
            self.root, self.checkpoints)

    def tearDown(self):
        self.temp.cleanup()

    def initialize(self, value):
        self.assertEqual(self.store.initialize_for_test(value).status, "SAVED")

    def adopt(self, job_id="job-a", **facts):
        return coordinator.adopt_job_durably(
            self.store, expected_job_id=job_id,
            occurred_at=facts.pop("occurred_at", UTC), **facts)

    def test_basic_durable_adoption_and_result_schema(self):
        self.initialize(snapshot(job()))
        receipt, result = self.adopt()
        persisted = self.store.load_queue().snapshot
        self.assertEqual((persisted.jobs[0].state, persisted.jobs[0].attempt_count),
                         (core.RUNNING, 1))
        self.assertEqual((persisted.revision, result.previous_revision,
                          result.resulting_revision), (1, 0, 1))
        self.assertTrue(result.durable)
        self.assertEqual(result.status, "EXECUTION_ADOPTED_DURABLY")
        self.assertEqual(set(result.to_dict()), {
            "adoption_version", "status", "job_id", "previous_revision",
            "resulting_revision", "previous_attempt_count",
            "resulting_attempt_count", "transition_class", "durable",
            "action_required", "reason_codes"})
        self.assertEqual(receipt.generation, ("job-a", 1))
        self.assertEqual(len(receipt.generation), 2)
        self.assertEqual(receipt.generation[1], receipt.running_job.attempt_count)

    def test_attempt_boundaries(self):
        for count, expected in ((1, 2), (2, 3)):
            with self.subTest(count=count):
                with tempfile.TemporaryDirectory() as path:
                    store = persistence.QueuePersistenceStore.for_test(
                        Path(path).resolve())
                    store.initialize_for_test(snapshot(job(attempt_count=count)))
                    receipt, result = coordinator.adopt_job_durably(
                        store, expected_job_id="job-a", occurred_at=UTC)
                    self.assertEqual(receipt.running_job.attempt_count, expected)
                    self.assertEqual(result.resulting_attempt_count, expected)

    def test_original_snapshot_immutable_order_and_other_jobs(self):
        original = snapshot(job("z", priority="P0"), job("job-a", priority="P1"),
                            job("tail", priority="P3"))
        before = original
        candidate = replace(original.jobs[1], state=core.RUNNING, attempt_count=1)
        updated = coordinator.replace_job_in_snapshot(original, candidate)
        self.assertEqual(original, before)
        self.assertEqual(tuple(value.job_id for value in updated.jobs),
                         ("z", "job-a", "tail"))
        self.assertEqual(updated.jobs[0], original.jobs[0])
        self.assertEqual(updated.jobs[2], original.jobs[2])
        self.assertEqual(updated.revision, original.revision)
        self.assertIs(updated.queue_identity, original.queue_identity)
        self.assertIs(updated.active_checkpoint_refs, original.active_checkpoint_refs)

    def test_replacement_missing_or_invalid_fails_closed(self):
        value = snapshot(job())
        self.assertIsNone(coordinator.replace_job_in_snapshot(value, job("other")))
        self.assertIsNone(coordinator.replace_job_in_snapshot({}, job()))
        self.assertIsNone(coordinator.replace_job_in_snapshot(value, {}))

    def test_target_active_ref_rejects_without_queue_write(self):
        target = job()
        saved = self.checkpoints.save_checkpoint(checkpoint(target))
        ref = persistence.ActiveCheckpointReference(
            persistence.REFERENCE_VERSION, target.job_id,
            saved.checkpoint_storage_id)
        self.initialize(snapshot(target, refs=(ref,)))
        before = self.store.queue_path.read_bytes()
        with mock.patch.object(self.store, "save_queue",
                               wraps=self.store.save_queue) as save:
            receipt, result = self.adopt()
        self.assertIsNone(receipt)
        self.assertEqual(result.reason_codes,
                         ("FRESH_ROUTE_CHECKPOINT_REFERENCE_PRESENT",))
        save.assert_not_called()
        self.assertEqual(self.store.queue_path.read_bytes(), before)

    def test_other_active_ref_is_preserved(self):
        other = job("other", state=core.CHECKPOINTED)
        saved = self.checkpoints.save_checkpoint(checkpoint(other))
        ref = persistence.ActiveCheckpointReference(
            persistence.REFERENCE_VERSION, other.job_id,
            saved.checkpoint_storage_id)
        self.initialize(snapshot(job("job-a", priority="P0"), other, refs=(ref,)))
        self.assertTrue(self.adopt()[1].durable)
        self.assertEqual(self.store.load_queue().snapshot.active_checkpoint_refs, (ref,))

    def test_core_rejections_do_not_save(self):
        cases = (
            job(attempt_count=3), job(state=core.RUNNING),
            job(requires_approval=True, risk_class=core.APPROVAL_REQUIRED),
            job(blocker_codes=("BLOCK",)),
        )
        for value in cases:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as path:
                    store = persistence.QueuePersistenceStore.for_test(Path(path).resolve())
                    store.initialize_for_test(snapshot(value))
                    before = store.queue_path.read_bytes()
                    receipt, result = coordinator.adopt_job_durably(
                        store, expected_job_id="job-a", occurred_at=UTC)
                    self.assertIsNone(receipt)
                    self.assertFalse(result.durable)
                    self.assertEqual(store.queue_path.read_bytes(), before)

    def test_dependency_risk_and_approval_are_delegated(self):
        approved = job("work", priority="P0", dependencies=("dep",),
                       requires_approval=True, approval_received=True,
                       risk_class=core.APPROVAL_REQUIRED)
        self.initialize(snapshot(job("dep", state=core.DONE), approved))
        self.assertTrue(self.adopt("work")[1].durable)

    def test_time_window_and_external_read_facts_pass_through(self):
        external = job(risk_class=core.EXTERNAL_READ, deadline_class="TIME_WINDOW")
        self.initialize(snapshot(external))
        before = self.store.queue_path.read_bytes()
        self.assertFalse(self.adopt(window_states={"job-a": "CLOSED"},
                                    external_read_allowed=True)[1].durable)
        self.assertEqual(self.store.queue_path.read_bytes(), before)
        self.assertTrue(self.adopt(window_states={"job-a": "OPEN"},
                                   external_read_allowed=True)[1].durable)

    def test_stale_revision_maps_conflict_without_retry(self):
        self.initialize(snapshot(job()))
        stale = persistence.QueueSaveResult(
            persistence.RESULT_VERSION, "STALE_REVISION", None,
            ("STALE_REVISION",))
        with mock.patch.object(self.store, "save_queue", return_value=stale) as save:
            receipt, result = self.adopt()
        self.assertIsNone(receipt)
        self.assertEqual(result.status, "ADOPTION_CONFLICT")
        self.assertFalse(result.durable)
        self.assertEqual(result.action_required, "RELOAD_AND_RESELECT")
        self.assertEqual(save.call_count, 1)

    def _concurrent(self, facts_a=None, facts_b=None):
        barrier = threading.Barrier(2)
        original_core = core.adopt_ready_job_for_execution

        def synchronized_core(*args, **kwargs):
            value = original_core(*args, **kwargs)
            barrier.wait(timeout=5)
            return value

        first_saved = threading.Event()
        original_save = self.store.save_queue

        def ordered_save(value, expected_revision):
            if threading.current_thread().name == "writer-b":
                first_saved.wait(timeout=5)
                return original_save(value, expected_revision)
            result = original_save(value, expected_revision)
            first_saved.set()
            return result

        outputs = {}

        def run(name, expected, facts):
            outputs[name] = coordinator.adopt_job_durably(
                self.store, expected_job_id=expected, occurred_at=UTC,
                **(facts or {}))

        with mock.patch.object(core, "adopt_ready_job_for_execution",
                               side_effect=synchronized_core), mock.patch.object(
                                   self.store, "save_queue", side_effect=ordered_save):
            a = threading.Thread(target=run, name="writer-a",
                                 args=("a", "job-a", facts_a))
            b = threading.Thread(target=run, name="writer-b",
                                 args=("b", "job-b" if facts_b else "job-a", facts_b))
            a.start(); b.start(); a.join(10); b.join(10)
        self.assertFalse(a.is_alive() or b.is_alive())
        return outputs

    def test_same_job_concurrent_one_success_one_conflict(self):
        self.initialize(snapshot(job()))
        outputs = self._concurrent()
        statuses = {value[1].status for value in outputs.values()}
        self.assertEqual(statuses,
                         {"EXECUTION_ADOPTED_DURABLY", "ADOPTION_CONFLICT"})
        persisted = self.store.load_queue().snapshot
        self.assertEqual((persisted.revision, persisted.jobs[0].attempt_count), (1, 1))

    def test_different_jobs_share_global_revision_conflict(self):
        self.initialize(snapshot(
            job("job-a", deadline_class="TIME_WINDOW"),
            job("job-b", deadline_class="TIME_WINDOW")))
        outputs = self._concurrent(
            {"window_states": {"job-a": "OPEN", "job-b": "CLOSED"}},
            {"window_states": {"job-a": "CLOSED", "job-b": "OPEN"}})
        self.assertEqual({value[1].status for value in outputs.values()},
                         {"EXECUTION_ADOPTED_DURABLY", "ADOPTION_CONFLICT"})
        self.assertEqual(self.store.load_queue().snapshot.revision, 1)

    def test_load_failures_never_call_core(self):
        for setup, expected in (
            (lambda: None, "MISSING_REQUIRES_BOOTSTRAP"),
            (lambda: (self.store.queue_path.parent.mkdir(parents=True),
                      self.store.queue_path.write_bytes(b"{")), "RECOVERY_BLOCKED"),
        ):
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as path:
                    store = persistence.QueuePersistenceStore.for_test(Path(path).resolve())
                    old = self.store; self.store = store
                    setup()
                    with mock.patch.object(core, "adopt_ready_job_for_execution") as adopt:
                        result = self.adopt()[1]
                    adopt.assert_not_called()
                    self.assertEqual(result.status, expected)
                    self.store = old

    def test_lock_and_manual_review_load_failures(self):
        for artifact, expected in (("lock", "LOCKED"),
                                   ("temp", "MANUAL_REVIEW_REQUIRED")):
            with self.subTest(artifact=artifact):
                with tempfile.TemporaryDirectory() as path:
                    store = persistence.QueuePersistenceStore.for_test(Path(path).resolve())
                    store.initialize_for_test(snapshot(job()))
                    getattr(store, artifact + "_path").write_bytes(b"fixture")
                    receipt, result = coordinator.adopt_job_durably(
                        store, expected_job_id="job-a", occurred_at=UTC)
                    self.assertIsNone(receipt)
                    self.assertEqual(result.status, expected)

    def test_known_save_failure_is_not_durable(self):
        self.initialize(snapshot(job()))
        blocked = persistence.QueueSaveResult(
            persistence.RESULT_VERSION, "RECOVERY_BLOCKED", None,
            ("PERSISTED_SNAPSHOT_INVALID",))
        with mock.patch.object(self.store, "save_queue", return_value=blocked):
            receipt, result = self.adopt()
        self.assertIsNone(receipt)
        self.assertFalse(result.durable)
        self.assertEqual(result.status, "RECOVERY_BLOCKED")

    def test_readback_uncertainty_has_no_receipt_rollback_or_second_save(self):
        self.initialize(snapshot(job()))
        original_save = self.store.save_queue
        calls = 0

        def save_then_uncertain(value, expected_revision):
            nonlocal calls
            calls += 1
            successful = original_save(value, expected_revision)
            self.assertEqual(successful.status, "SAVED")
            return persistence.QueueSaveResult(
                persistence.RESULT_VERSION, "RECOVERY_BLOCKED", None,
                ("QUEUE_READ_BACK_FAILED",))

        with mock.patch.object(self.store, "save_queue",
                               side_effect=save_then_uncertain):
            receipt, result = self.adopt()
        self.assertIsNone(receipt)
        self.assertEqual(result.status, "EXECUTION_ADOPTION_UNCERTAIN")
        self.assertEqual(result.action_required, "RECOVERY_REQUIRED")
        self.assertEqual(calls, 1)
        persisted = self.store.load_queue().snapshot.jobs[0]
        self.assertEqual((persisted.state, persisted.attempt_count), (core.RUNNING, 1))

    def test_saved_uses_no_second_load(self):
        self.initialize(snapshot(job()))
        with mock.patch.object(self.store, "load_queue",
                               wraps=self.store.load_queue) as load:
            self.assertTrue(self.adopt()[1].durable)
        self.assertEqual(load.call_count, 1)

    def test_core_result_is_reused_and_validators_invoked(self):
        self.initialize(snapshot(job()))
        with mock.patch.object(core, "validate_execution_adoption_transition",
                               wraps=core.validate_execution_adoption_transition) as detailed, \
             mock.patch.object(core, "validate_job_transition_result",
                               wraps=core.validate_job_transition_result) as shared:
            receipt, result = self.adopt()
        self.assertTrue(result.durable)
        detailed.assert_called()
        shared.assert_called()
        self.assertEqual(receipt.transition_result.reason_code,
                         "JOB_EXECUTION_ADOPTION")

    def test_invalid_core_output_blocks_save(self):
        self.initialize(snapshot(job()))
        _, real_transition = core.adopt_ready_job_for_execution(
            (job(),), expected_job_id="job-a", occurred_at=UTC)
        bad_candidate = replace(job(), state=core.RUNNING, attempt_count=2)
        with mock.patch.object(core, "adopt_ready_job_for_execution",
                               return_value=(bad_candidate, real_transition)), \
             mock.patch.object(self.store, "save_queue") as save:
            receipt, result = self.adopt()
        self.assertIsNone(receipt)
        self.assertEqual(result.reason_codes,
                         ("CORE_TRANSITION_VALIDATION_FAILED",))
        save.assert_not_called()

    def test_crash_before_and_after_cas_models(self):
        self.initialize(snapshot(job()))
        loaded = self.store.load_queue().snapshot
        candidate, _ = core.adopt_ready_job_for_execution(
            loaded.jobs, expected_job_id="job-a", occurred_at=UTC)
        self.assertEqual(self.store.load_queue().snapshot.jobs[0].state, core.READY)
        updated = coordinator.replace_job_in_snapshot(loaded, candidate)
        self.assertEqual(self.store.save_queue(updated, 0).status, "SAVED")
        after = self.store.load_queue().snapshot
        self.assertEqual((after.jobs[0].state, after.jobs[0].attempt_count),
                         (core.RUNNING, 1))

    def test_restart_running_is_not_readopted(self):
        self.initialize(snapshot(job(state=core.RUNNING, attempt_count=1)))
        receipt, result = self.adopt()
        self.assertIsNone(receipt)
        self.assertFalse(result.durable)
        self.assertEqual(self.store.load_queue().snapshot.jobs[0].attempt_count, 1)

    def test_result_and_receipt_are_frozen_and_safe(self):
        self.initialize(snapshot(job()))
        receipt, result = self.adopt()
        with self.assertRaises(FrozenInstanceError):
            result.durable = False
        with self.assertRaises(FrozenInstanceError):
            receipt.resulting_revision = 9
        rendered = repr(result.to_dict())
        for forbidden in (str(self.root), "payload", "raw_exception", "secret"):
            self.assertNotIn(forbidden, rendered.lower())

    def test_invalid_inputs_do_not_echo_or_raise(self):
        self.initialize(snapshot(job()))
        for identifier in (None, {}, "C:/private", "fixture-secret"):
            receipt, result = coordinator.adopt_job_durably(
                self.store, expected_job_id=identifier, occurred_at=UTC)
            self.assertIsNone(receipt)
            if isinstance(identifier, str):
                self.assertNotIn(identifier, repr(result))

    def test_no_production_or_checkpoint_write_and_no_execution_surfaces(self):
        production_queue = ROOT / "runtime" / "unattended-queue-v0.1.json"
        production_checkpoints = ROOT / "runtime" / "checkpoints"
        self.assertFalse(production_queue.exists())
        self.assertFalse(production_checkpoints.exists())
        source = (ROOT / "scripts" / "job_execution_adoption_coordinator.py").read_text(
            encoding="utf-8")
        for forbidden in ("subprocess", "execute(", "send_notification",
                          "save_checkpoint(", "bootstrap_production_queue"):
            self.assertNotIn(forbidden, source)
        self.initialize(snapshot(job()))
        self.assertTrue(self.adopt()[1].durable)
        self.assertFalse(production_queue.exists())
        self.assertFalse(production_checkpoints.exists())


if __name__ == "__main__":
    unittest.main()
