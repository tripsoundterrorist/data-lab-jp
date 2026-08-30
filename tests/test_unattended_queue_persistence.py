from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import unattended_checkpoint_storage as checkpoints  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402


def job(job_id="job-a", **changes):
    value = core.JobContract(
        queue_version="0.1", job_id=job_id, job_type="static_validation",
        priority="P2", risk_class=core.READ_ONLY, dependencies=(), blocker_codes=(),
        requires_approval=False, retry_policy="TRANSIENT_ONLY", max_attempts=3,
        checkpoint_supported=True, created_at="2026-08-30T00:00:00Z",
        deadline_class="NONE",
    )
    return replace(value, **changes)


def checkpoint(value):
    result = core.create_checkpoint(
        value, last_completed_step="STEP_ONE", resume_preconditions=("GIT_CLEAN",),
        checkpoint_time="2026-08-30T00:01:00Z", reason_codes=("SAFE_PAUSE",),
    )
    assert result is not None
    return result


def snapshot(*jobs, revision=0, refs=()):
    return persistence.PersistedQueueSnapshot(core.get_queue_identity(), revision,
                                              tuple(jobs), tuple(refs))


class PurePersistenceTests(unittest.TestCase):
    def test_empty_roundtrip_is_exact_and_deterministic(self):
        value = snapshot()
        first = persistence.serialize_queue(value)
        self.assertEqual(first, persistence.serialize_queue(value))
        self.assertEqual(persistence.deserialize_queue(first).snapshot, value)
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertFalse(first.endswith(b"\n"))

    def test_non_empty_roundtrip_preserves_all_fields_and_order(self):
        jobs = (job("b", state=core.WAITING_APPROVAL, requires_approval=True),
                job("a", attempt_count=2, approval_received=False))
        loaded = persistence.deserialize_queue(persistence.serialize_queue(snapshot(*jobs)))
        self.assertEqual(loaded.snapshot.jobs, jobs)
        self.assertEqual(set(json.loads(persistence.serialize_queue(snapshot(*jobs)))["jobs"][0]), {
            "queue_version", "job_id", "job_type", "priority", "risk_class",
            "dependencies", "blocker_codes", "requires_approval", "retry_policy",
            "max_attempts", "checkpoint_supported", "created_at", "deadline_class",
            "state", "attempt_count", "approval_received",
        })

    def test_refs_must_be_sorted_unique_known_and_exact(self):
        a = persistence.ActiveCheckpointReference("0.1", "a", "a" * 64)
        b = persistence.ActiveCheckpointReference("0.1", "b", "b" * 64)
        self.assertIsNotNone(persistence.serialize_queue(snapshot(job("a"), job("b"), refs=(a, b))))
        for refs in ((b, a), (a, a), (persistence.ActiveCheckpointReference("0.1", "x", "c" * 64),)):
            self.assertIsNone(persistence.serialize_queue(snapshot(job("a"), job("b"), refs=refs)))

    def test_duplicate_json_key_is_rejected(self):
        content = persistence.serialize_queue(snapshot())
        bad = content.replace(b'"revision":0', b'"revision":0,"revision":0')
        self.assertEqual(persistence.deserialize_queue(bad).status, "RECOVERY_BLOCKED")

    def test_unknown_envelope_job_and_ref_fields_are_rejected(self):
        base = json.loads(persistence.serialize_queue(snapshot(job())))
        cases = []
        envelope = dict(base); envelope["extra"] = True; cases.append(envelope)
        job_extra = json.loads(json.dumps(base)); job_extra["jobs"][0]["payload"] = {}; cases.append(job_extra)
        ref_extra = json.loads(json.dumps(base)); ref_extra["active_checkpoint_refs"] = [{
            "reference_version": "0.1", "job_id": "job-a",
            "checkpoint_storage_id": "a" * 64, "extra": True}]; cases.append(ref_extra)
        for value in cases:
            content = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
            self.assertEqual(persistence.deserialize_queue(content).status, "RECOVERY_BLOCKED")

    def test_wrong_versions_identity_and_noncanonical_bytes_reject(self):
        base = json.loads(persistence.serialize_queue(snapshot()))
        for key, value in (("persistence_version", "9"), ("queue_version", "9"),
                           ("queue_id", "unapproved")):
            changed = dict(base); changed[key] = value
            content = json.dumps(changed, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
            self.assertEqual(persistence.deserialize_queue(content).status, "RECOVERY_BLOCKED")
        self.assertEqual(persistence.deserialize_queue(persistence.serialize_queue(snapshot()) + b"\n").status,
                         "RECOVERY_BLOCKED")

    def test_core_dependency_validation_is_delegated(self):
        invalid = snapshot(job("a", dependencies=("missing",)))
        self.assertFalse(core.validate_queue(invalid.jobs)[0])
        self.assertIsNone(persistence.serialize_queue(invalid))

    def test_reference_replacement_and_same_ref(self):
        base = snapshot(job())
        first = persistence.replace_active_checkpoint_ref(base, "job-a", "a" * 64)
        self.assertEqual(first.status, "UPDATED")
        same = persistence.replace_active_checkpoint_ref(first.snapshot, "job-a", "a" * 64)
        self.assertEqual(same.status, "NO_CHANGE")
        self.assertEqual(same.snapshot.revision, 0)
        second = persistence.replace_active_checkpoint_ref(first.snapshot, "job-a", "b" * 64)
        self.assertEqual(second.snapshot.active_checkpoint_refs[0].checkpoint_storage_id, "b" * 64)

    def test_restart_states_are_not_rewritten(self):
        states = (core.WAITING_APPROVAL, core.FAILED_SAFE, core.DONE, core.RUNNING, core.CHECKPOINTED)
        jobs = tuple(job(f"job-{index}", state=state) for index, state in enumerate(states))
        loaded = persistence.deserialize_queue(persistence.serialize_queue(snapshot(*jobs)))
        self.assertEqual(tuple(value.state for value in loaded.snapshot.jobs), states)

    def test_no_input_payload_or_transition_apis(self):
        content = persistence.serialize_queue(snapshot(job()))
        for forbidden in (b"payload", b"handler", b"next_retry_at", b"raw_exception"):
            self.assertNotIn(forbidden, content)
        for name in ("enqueue", "resume", "approve", "retry", "cleanup"):
            self.assertFalse(hasattr(persistence, name))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.cp = checkpoints.CheckpointStorage.for_test(self.root, core.get_queue_identity())
        self.store = persistence.QueuePersistenceStore.for_test(self.root, self.cp)

    def tearDown(self):
        self.temp.cleanup()

    def initialize(self, value):
        result = self.store.initialize_for_test(value)
        self.assertEqual(result.status, "SAVED")

    def test_missing_queue_requires_bootstrap_without_creation(self):
        result = self.store.load_queue()
        self.assertEqual(result.status, "MISSING_REQUIRES_BOOTSTRAP")
        self.assertFalse(self.store.queue_path.exists())

    def test_revision_cas_and_stale_writer(self):
        self.initialize(snapshot(job()))
        loaded = self.store.load_queue().snapshot
        saved = self.store.save_queue(loaded, 0)
        self.assertEqual((saved.status, saved.revision), ("SAVED", 1))
        self.assertEqual(self.store.save_queue(loaded, 0).status, "STALE_REVISION")

    def test_lock_contention_does_not_force_unlock(self):
        self.initialize(snapshot())
        self.store.lock_path.write_bytes(b"existing")
        result = self.store.save_queue(snapshot(), 0)
        self.assertEqual(result.status, "LOCKED")
        self.assertTrue(self.store.lock_path.exists())

    def test_temp_residue_is_not_promoted(self):
        self.initialize(snapshot())
        before = self.store.queue_path.read_bytes()
        self.store.temp_path.write_bytes(b"partial")
        self.assertEqual(self.store.load_queue().status, "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(self.store.queue_path.read_bytes(), before)
        self.assertEqual(self.store.save_queue(snapshot(), 0).status, "MANUAL_REVIEW_REQUIRED")

    def test_atomic_save_leaves_no_temp_and_readback_is_valid(self):
        self.initialize(snapshot(job()))
        result = self.store.save_queue(self.store.load_queue().snapshot, 0)
        self.assertEqual(result.status, "SAVED")
        self.assertFalse(self.store.temp_path.exists())
        self.assertEqual(self.store.load_queue().snapshot.revision, 1)

    def test_object_first_reference_second_and_old_object_retained(self):
        cp_job = job(state=core.CHECKPOINTED)
        self.initialize(snapshot(cp_job))
        old = self.cp.save_checkpoint(checkpoint(cp_job))
        adopted = persistence.replace_active_checkpoint_ref(
            self.store.load_queue().snapshot, cp_job.job_id, old.checkpoint_storage_id)
        self.assertEqual(self.store.save_queue(adopted.snapshot, 0).status, "SAVED")
        newer_checkpoint = replace(checkpoint(cp_job), checkpoint_time="2026-08-30T00:02:00Z")
        new = self.cp.save_checkpoint(newer_checkpoint)
        current = self.store.load_queue().snapshot
        adopted_new = persistence.replace_active_checkpoint_ref(
            current, cp_job.job_id, new.checkpoint_storage_id)
        self.assertEqual(self.store.save_queue(adopted_new.snapshot, 1).status, "SAVED")
        self.assertTrue((self.cp.objects_dir / f"{old.checkpoint_storage_id}.json").exists())

    def test_crash_after_object_save_leaves_queue_unchanged_and_unreferenced(self):
        cp_job = job(state=core.CHECKPOINTED)
        self.initialize(snapshot(cp_job))
        before = self.store.queue_path.read_bytes()
        self.cp.save_checkpoint(checkpoint(cp_job))
        self.assertEqual(self.store.queue_path.read_bytes(), before)
        self.assertEqual(self.cp.inspect(()).status, "UNREFERENCED_OBJECTS_PRESENT")

    def test_missing_referenced_object_blocks_load_and_save(self):
        cp_job = job(state=core.CHECKPOINTED)
        ref = persistence.ActiveCheckpointReference("0.1", cp_job.job_id, "a" * 64)
        self.initialize(snapshot(cp_job, refs=(ref,)))
        self.assertEqual(self.store.load_queue().status, "RECOVERY_BLOCKED")
        self.assertEqual(self.store.save_queue(snapshot(cp_job, refs=(ref,)), 0).status,
                         "RECOVERY_BLOCKED")

    def test_checkpointed_without_ref_is_valid_but_inspection_requires_review(self):
        cp_job = job(state=core.CHECKPOINTED)
        self.initialize(snapshot(cp_job))
        self.assertEqual(self.store.load_queue().status, "HEALTHY")
        report = self.store.inspect_queue_storage()
        self.assertEqual(report.status, "MANUAL_REVIEW_REQUIRED")
        self.assertIn("CHECKPOINTED_REFERENCE_ABSENT", report.reason_codes)

    def test_malformed_queue_is_not_repaired(self):
        self.store.queue_path.parent.mkdir(parents=True)
        self.store.queue_path.write_bytes(b"{")
        self.assertEqual(self.store.load_queue().status, "RECOVERY_BLOCKED")
        self.assertEqual(self.store.queue_path.read_bytes(), b"{")

    def test_cwd_independence_and_arbitrary_constructor_rejection(self):
        self.initialize(snapshot())
        original = Path.cwd()
        try:
            import os
            os.chdir(self.root)
            self.assertEqual(self.store.load_queue().status, "HEALTHY")
        finally:
            os.chdir(original)
        with self.assertRaises(ValueError):
            persistence.QueuePersistenceStore(Path("relative"), None, object())

    def test_production_runtime_is_not_the_test_root(self):
        self.assertNotEqual(self.store.queue_path, ROOT / "runtime" / "unattended-queue-v0.1.json")
        self.initialize(snapshot())
        self.assertFalse((ROOT / "runtime" / "unattended-queue-v0.1.json").exists())


if __name__ == "__main__":
    unittest.main()
