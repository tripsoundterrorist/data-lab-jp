from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import unattended_checkpoint_storage as checkpoints  # noqa: E402
import unattended_job_queue as core  # noqa: E402
import unattended_queue_persistence as persistence  # noqa: E402


class ProductionPathTests(unittest.TestCase):
    def setUp(self):
        self.queue_path = ROOT / "runtime" / "unattended-queue-v0.1.json"
        self.checkpoint_root = (ROOT / "runtime" / "checkpoints"
                                / core.MAIN_QUEUE_ID / "objects")
        self.assertFalse(self.queue_path.exists())
        self.assertFalse((ROOT / "runtime" / "checkpoints").exists())

    def tearDown(self):
        self.assertFalse(self.queue_path.exists())
        self.assertFalse((ROOT / "runtime" / "checkpoints").exists())

    def test_formal_root_and_paths_are_exact_and_cwd_independent(self):
        self.assertEqual(persistence.FORMAL_REPO_ROOT, ROOT)
        self.assertEqual(checkpoints.FORMAL_REPO_ROOT, ROOT)
        expected_queue = ROOT / "runtime" / "unattended-queue-v0.1.json"
        expected_checkpoints = ROOT / "runtime" / "checkpoints" / core.MAIN_QUEUE_ID / "objects"
        original = Path.cwd()
        try:
            os.chdir(ROOT.parent)
            self.assertEqual(persistence.resolve_production_queue_path(), expected_queue)
            self.assertEqual(persistence.resolve_production_checkpoint_root(), expected_checkpoints)
        finally:
            os.chdir(original)

    def test_unapproved_identity_cannot_resolve_checkpoint_path(self):
        invalid = core.QueueIdentity("0.1", "other", "CONFIGURED",
                                     "POLICY_BACKED_LOGICAL_IDENTITY")
        self.assertIsNone(persistence.resolve_production_checkpoint_root(invalid))

    def test_missing_production_queue_requires_bootstrap_without_creation(self):
        before_runtime = {item.name for item in (ROOT / "runtime").iterdir()}
        loaded = persistence.load_production_queue_read_only()
        report = persistence.inspect_production_queue_storage()
        after_runtime = {item.name for item in (ROOT / "runtime").iterdir()}
        self.assertEqual(loaded.status, "MISSING_REQUIRES_BOOTSTRAP")
        self.assertEqual(report.status, "MISSING_REQUIRES_BOOTSTRAP")
        self.assertEqual(report.checkpoint_status, "MISSING_EMPTY_STORAGE_ALLOWED")
        self.assertFalse(report.queue_exists)
        self.assertFalse(report.checkpoint_storage_exists)
        self.assertEqual(before_runtime, after_runtime)

    def test_production_write_and_bootstrap_are_disabled(self):
        identity = core.get_queue_identity()
        cp = checkpoints.CheckpointStorage._for_read_only(ROOT, identity)
        store = persistence.QueuePersistenceStore._for_read_only(ROOT, cp)
        empty = persistence.PersistedQueueSnapshot(identity, 0, (), ())
        self.assertEqual(store.initialize_for_test(empty).status, "WRITE_DISABLED")
        self.assertEqual(store.save_queue(empty, 0).status, "WRITE_DISABLED")
        invalid_checkpoint = core.Checkpoint("job-a", core.CHECKPOINTED, "STEP", (), (), 0,
                                             "2026-08-30T00:00:00Z", ("SAFE_PAUSE",))
        self.assertEqual(cp.save_checkpoint(invalid_checkpoint).status, "WRITE_DISABLED")

    def test_formal_root_cannot_be_injected_as_test_write_root(self):
        with self.assertRaises(ValueError):
            checkpoints.CheckpointStorage.for_test(ROOT, core.get_queue_identity())
        with self.assertRaises(ValueError):
            persistence.QueuePersistenceStore.for_test(ROOT)

    def test_safe_inspection_has_no_raw_identity_or_path_fields(self):
        report = persistence.inspect_production_queue_storage()
        fields = set(vars(report))
        for forbidden in ("job_id", "checkpoint_storage_id", "path", "exception", "payload"):
            self.assertNotIn(forbidden, fields)
        rendered = repr(report)
        self.assertNotIn(str(ROOT), rendered)
        self.assertNotIn(core.MAIN_QUEUE_ID, rendered)

    def test_no_production_activation_functions_exist(self):
        for name in ("save_production_queue", "bootstrap_production_queue",
                     "save_production_checkpoint"):
            self.assertFalse(hasattr(persistence, name))
            self.assertFalse(hasattr(checkpoints, name))

    def test_gitignore_is_minimal_and_preserves_evidence(self):
        ignored_queue = subprocess.run(
            ["git", "check-ignore", "runtime/unattended-queue-v0.1.json"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        ignored_checkpoint = subprocess.run(
            ["git", "check-ignore", "runtime/checkpoints/x/objects/y.json"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        evidence = subprocess.run(
            ["git", "check-ignore", "runtime/evidence/new-review.json"],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(ignored_queue.returncode, 0)
        self.assertEqual(ignored_checkpoint.returncode, 0)
        self.assertNotEqual(evidence.returncode, 0)


class ReadOnlyFixtureTests(unittest.TestCase):
    """Production-format read tests use an isolated root and never formal runtime."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.identity = core.get_queue_identity()
        self.cp_writer = checkpoints.CheckpointStorage.for_test(self.root, self.identity)
        self.writer = persistence.QueuePersistenceStore.for_test(self.root, self.cp_writer)
        self.cp_reader = checkpoints.CheckpointStorage._for_read_only(self.root, self.identity)
        self.reader = persistence.QueuePersistenceStore._for_read_only(self.root, self.cp_reader)

    def tearDown(self):
        self.temp.cleanup()

    def empty(self):
        return persistence.PersistedQueueSnapshot(self.identity, 0, (), ())

    def test_temporary_store_unchanged_and_read_only_mode_cannot_write(self):
        self.assertEqual(self.writer.initialize_for_test(self.empty()).status, "SAVED")
        before = self.writer.queue_path.read_bytes()
        self.assertEqual(self.reader.load_queue().status, "HEALTHY")
        self.assertEqual(self.reader.save_queue(self.empty(), 0).status, "WRITE_DISABLED")
        self.assertEqual(self.writer.queue_path.read_bytes(), before)

    def test_malformed_duplicate_wrong_version_and_unknown_field_block(self):
        self.writer.queue_path.parent.mkdir(parents=True)
        cases = [b"{", b'{"revision":0,"revision":0}',
                 json.dumps({"persistence_version": "9"}).encode(),
                 json.dumps({"unknown": True}).encode()]
        for content in cases:
            self.writer.queue_path.write_bytes(content)
            self.assertEqual(self.reader.load_queue().status, "RECOVERY_BLOCKED")

    def test_active_missing_object_and_directory_block(self):
        job = core.JobContract(
            "0.1", "job-a", "static_validation", "P2", core.READ_ONLY, (), (),
            False, "NONE", 1, True, "2026-08-30T00:00:00Z", "NONE",
            state=core.CHECKPOINTED)
        ref = persistence.ActiveCheckpointReference("0.1", "job-a", "a" * 64)
        value = persistence.PersistedQueueSnapshot(self.identity, 0, (job,), (ref,))
        self.assertEqual(self.writer.initialize_for_test(value).status, "SAVED")
        self.assertEqual(self.reader.load_queue().status, "RECOVERY_BLOCKED")
        self.assertEqual(self.cp_reader.inspect(("a" * 64,)).status, "RECOVERY_BLOCKED")

    def test_active_corrupt_cross_job_cross_queue_block(self):
        job = core.JobContract(
            "0.1", "job-a", "static_validation", "P2", core.READ_ONLY, (), (),
            False, "NONE", 1, True, "2026-08-30T00:00:00Z", "NONE",
            state=core.CHECKPOINTED)
        checkpoint = core.create_checkpoint(
            job, last_completed_step="STEP", resume_preconditions=(),
            checkpoint_time="2026-08-30T00:01:00Z", reason_codes=("SAFE_PAUSE",))
        saved = self.cp_writer.save_checkpoint(checkpoint)
        self.assertEqual(self.cp_reader.load_checkpoint(saved.checkpoint_storage_id, "job-b").status,
                         "RECOVERY_BLOCKED")
        path = self.cp_writer.objects_dir / f"{saved.checkpoint_storage_id}.json"
        path.write_bytes(b"{")
        self.assertEqual(self.cp_reader.load_checkpoint(saved.checkpoint_storage_id, "job-a").status,
                         "RECOVERY_BLOCKED")

        value = json.loads(checkpoints.checkpoint_object_bytes(self.identity, checkpoint))
        value["queue_id"] = "other"
        content = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        import hashlib
        other_id = hashlib.sha256(content).hexdigest()
        (self.cp_writer.objects_dir / f"{other_id}.json").write_bytes(content)
        self.assertIn("REFERENCE_QUEUE_MISMATCH",
                      self.cp_reader.load_checkpoint(other_id, "job-a").reason_codes)

    def test_unreferenced_historical_semantics_are_preserved(self):
        job = core.JobContract(
            "0.1", "job-a", "static_validation", "P2", core.READ_ONLY, (), (),
            False, "NONE", 1, True, "2026-08-30T00:00:00Z", "NONE",
            state=core.CHECKPOINTED)
        checkpoint = core.create_checkpoint(
            job, last_completed_step="STEP", resume_preconditions=(),
            checkpoint_time="2026-08-30T00:01:00Z", reason_codes=("SAFE_PAUSE",))
        self.cp_writer.save_checkpoint(checkpoint)
        report = self.cp_reader.inspect(())
        self.assertEqual(report.status, "UNREFERENCED_OBJECTS_PRESENT")
        self.assertIsNone(report.confirmed_orphan_count)


if __name__ == "__main__":
    unittest.main()
