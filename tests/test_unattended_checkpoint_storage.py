from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import unattended_checkpoint_storage as storage  # noqa: E402
import unattended_job_queue as core  # noqa: E402


def job(job_id="job-a", **changes):
    value = core.JobContract(
        queue_version="0.1", job_id=job_id, job_type="static_validation",
        priority="P2", risk_class=core.READ_ONLY, dependencies=(), blocker_codes=(),
        requires_approval=False, retry_policy="NONE", max_attempts=3,
        checkpoint_supported=True, created_at="2026-08-30T00:00:00Z",
        deadline_class="NONE", state=core.CHECKPOINTED,
    )
    return replace(value, **changes)


def checkpoint(job_id="job-a", **changes):
    value = core.create_checkpoint(
        job(job_id), last_completed_step="STEP_ONE",
        resume_preconditions=("GIT_CLEAN",), checkpoint_time="2026-08-30T00:01:00Z",
        reason_codes=("SAFE_PAUSE",),
    )
    assert value is not None
    return replace(value, **changes)


class CheckpointStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.identity = core.get_queue_identity()
        self.store = storage.CheckpointStorage.for_test(self.root, self.identity)

    def tearDown(self):
        self.temp.cleanup()

    def test_canonical_object_is_deterministic_compact_and_bounded(self):
        first = storage.checkpoint_object_bytes(self.identity, checkpoint())
        second = storage.checkpoint_object_bytes(self.identity, checkpoint())
        self.assertEqual(first, second)
        self.assertNotIn(b"\n", first)
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertLessEqual(len(first), storage.MAX_CHECKPOINT_BYTES)

    def test_storage_id_is_exact_sha256(self):
        content = storage.checkpoint_object_bytes(self.identity, checkpoint())
        self.assertEqual(storage.checkpoint_storage_id(content), hashlib.sha256(content).hexdigest())

    def test_valid_roundtrip_and_idempotent_save(self):
        saved = self.store.save_checkpoint(checkpoint())
        self.assertEqual(saved.status, "SAVED")
        loaded = self.store.load_checkpoint(saved.checkpoint_storage_id, "job-a")
        self.assertEqual(loaded.status, "HEALTHY")
        self.assertEqual(loaded.checkpoint, checkpoint())
        self.assertEqual(self.store.save_checkpoint(checkpoint()).status, "NO_CHANGE")

    def test_core_checkpoint_validation_is_delegated(self):
        invalid = replace(checkpoint(), last_completed_step="secret")
        self.assertFalse(core.validate_checkpoint(invalid)[0])
        self.assertEqual(self.store.save_checkpoint(invalid).status, "RECOVERY_BLOCKED")

    def test_digest_mismatch_blocks(self):
        saved = self.store.save_checkpoint(checkpoint())
        path = self.store.objects_dir / f"{saved.checkpoint_storage_id}.json"
        path.write_bytes(path.read_bytes() + b" ")
        result = self.store.load_checkpoint(saved.checkpoint_storage_id, "job-a")
        self.assertIn("CHECKPOINT_DIGEST_MISMATCH", result.reason_codes)

    def test_cross_job_mismatch_blocks(self):
        saved = self.store.save_checkpoint(checkpoint())
        result = self.store.load_checkpoint(saved.checkpoint_storage_id, "job-b")
        self.assertIn("REFERENCE_JOB_MISMATCH", result.reason_codes)

    def test_cross_queue_mismatch_blocks(self):
        value = json.loads(storage.checkpoint_object_bytes(self.identity, checkpoint()))
        value["queue_id"] = "another-queue"
        content = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
        object_id = hashlib.sha256(content).hexdigest()
        self.store.objects_dir.mkdir(parents=True)
        (self.store.objects_dir / f"{object_id}.json").write_bytes(content)
        result = self.store.load_checkpoint(object_id, "job-a")
        self.assertIn("REFERENCE_QUEUE_MISMATCH", result.reason_codes)

    def test_missing_reference_is_not_empty_checkpoint(self):
        result = self.store.load_checkpoint("0" * 64, "job-a")
        self.assertEqual(result.status, "REFERENCE_MISSING")
        self.store.objects_dir.mkdir(parents=True)
        self.assertEqual(self.store.inspect(("0" * 64,)).status, "RECOVERY_BLOCKED")

    def test_unreferenced_object_is_not_called_orphan(self):
        self.store.save_checkpoint(checkpoint())
        result = self.store.inspect(())
        self.assertEqual(result.status, "UNREFERENCED_OBJECTS_PRESENT")
        self.assertEqual(result.unreferenced_object_count, 1)
        self.assertIsNone(result.confirmed_orphan_count)

    def test_active_and_historical_objects_are_retained(self):
        old = self.store.save_checkpoint(checkpoint())
        new = self.store.save_checkpoint(checkpoint(checkpoint_time="2026-08-30T00:02:00Z"))
        report = self.store.inspect((new.checkpoint_storage_id,))
        self.assertEqual(report.checkpoint_object_count, 2)
        self.assertEqual(report.unreferenced_object_count, 1)
        self.assertTrue((self.store.objects_dir / f"{old.checkpoint_storage_id}.json").exists())

    def test_corrupt_active_blocks_but_corrupt_historical_requires_review(self):
        active = self.store.save_checkpoint(checkpoint())
        path = self.store.objects_dir / f"{active.checkpoint_storage_id}.json"
        path.write_bytes(b"{")
        self.assertEqual(self.store.inspect((active.checkpoint_storage_id,)).status, "RECOVERY_BLOCKED")
        self.assertEqual(self.store.inspect(()).status, "MANUAL_REVIEW_REQUIRED")

    def test_temp_residue_requires_manual_review(self):
        self.store.objects_dir.mkdir(parents=True)
        (self.store.objects_dir / ("0" * 64 + ".json.tmp")).write_bytes(b"partial")
        self.assertEqual(self.store.inspect(()).status, "MANUAL_REVIEW_REQUIRED")

    def test_missing_directory_is_allowed_only_as_empty_storage(self):
        result = self.store.inspect(())
        self.assertEqual(result.status, "MISSING_EMPTY_STORAGE_ALLOWED")
        self.assertFalse(self.store.objects_dir.exists())
        self.assertEqual(self.store.inspect(("0" * 64,)).status, "RECOVERY_BLOCKED")

    def test_unknown_fields_and_versions_block(self):
        value = json.loads(storage.checkpoint_object_bytes(self.identity, checkpoint()))
        for change in ("extra", "version"):
            changed = dict(value)
            if change == "extra":
                changed["extra"] = True
            else:
                changed["checkpoint_storage_version"] = "9"
            content = json.dumps(changed, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
            object_id = hashlib.sha256(content).hexdigest()
            self.store.objects_dir.mkdir(parents=True, exist_ok=True)
            (self.store.objects_dir / f"{object_id}.json").write_bytes(content)
            self.assertEqual(self.store.load_checkpoint(object_id, "job-a").status, "RECOVERY_BLOCKED")

    def test_path_and_store_constructor_reject_arbitrary_values(self):
        with self.assertRaises(ValueError):
            storage.CheckpointStorage(Path("relative"), self.identity, object())
        self.assertEqual(self.store.load_checkpoint("../bad", "job-a").status, "RECOVERY_BLOCKED")

    def test_symlink_root_is_rejected_when_supported(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable in this Windows context")
        with self.assertRaises(ValueError):
            storage.CheckpointStorage.for_test(link, self.identity)

    def test_secret_payload_and_delete_api_are_absent(self):
        content = storage.checkpoint_object_bytes(self.identity, checkpoint())
        for forbidden in (b"payload", b"handler", b"raw_exception", b"credential"):
            self.assertNotIn(forbidden, content)
        self.assertFalse(hasattr(self.store, "delete_checkpoint"))


if __name__ == "__main__":
    unittest.main()
