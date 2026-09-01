from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_evidence as evidence_core  # noqa: E402
import development_remote_approval_replay_persistence as persistence  # noqa: E402
import development_remote_approval_replay_record as codec  # noqa: E402
import development_remote_iphone_approval_observation as approval  # noqa: E402


NOW = 2_000_000_000
SHA = "a" * 40


def evidence():
    return evidence_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref="b" * 64, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=50,
        approval_status="REQUIRED",
    )


def observation(**changes):
    values = {
        "observation_version": approval.OBSERVATION_VERSION,
        "source": approval.APPROVED_SOURCE,
        "repository": approval.APPROVED_REPOSITORY,
        "device_class": approval.APPROVED_DEVICE_CLASS,
        "request_id": "approval-pr-50",
        "current_gate_id": "current-gate",
        "next_gate_id": "next-gate",
        "head_sha": SHA,
        "ci_run_id": 50,
        "status": "APPROVED",
        "requested_at_epoch_s": NOW - 60,
        "decided_at_epoch_s": NOW,
    }
    values.update(changes)
    return approval.RemoteApprovalObservation(**values)


def record(**changes):
    observed = observation()
    action = approval.observe(evidence(), observed, evaluated_at_epoch_s=NOW)
    value = codec.build_record(observed, action)
    assert value is not None
    value.update(changes)
    return value


class RemoteApprovalReplayPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="approval-replay-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.store = persistence.RemoteApprovalReplayStore.for_test(self.root)

    def initialize(self):
        result = self.store.initialize_for_test()
        self.assertEqual((result.status, result.revision), ("SAVED", 0))

    def test_missing_store_requires_explicit_bootstrap(self):
        result = self.store.load()
        self.assertEqual(result.status, "MISSING_REQUIRES_BOOTSTRAP")
        self.assertFalse(self.store.path.exists())

    def test_bootstrap_and_load_are_exact(self):
        self.initialize()
        loaded = self.store.load()
        self.assertEqual((loaded.status, loaded.revision, loaded.records),
                         ("HEALTHY", 0, ()))
        self.assertFalse(self.store.path.read_bytes().endswith(b"\n"))

    def test_cas_save_and_stale_writer(self):
        self.initialize()
        saved = self.store.save_record(record(), 0)
        self.assertEqual((saved.status, saved.revision), ("SAVED", 1))
        loaded = self.store.load()
        self.assertEqual((loaded.revision, len(loaded.records)), (1, 1))
        stale = self.store.save_record(
            record(request_id="approval-pr-51", next_gate_id="later-gate",
                   head_sha="c" * 40, ci_run_id=51), 0,
        )
        self.assertEqual(stale.status, "STALE_REVISION")

    def test_exact_replay_is_not_written_twice(self):
        self.initialize()
        value = record()
        self.assertEqual(self.store.save_record(value, 0).status, "SAVED")
        before = self.store.path.read_bytes()
        result = self.store.save_record(value, 1)
        self.assertEqual((result.status, result.revision),
                         ("ALREADY_CONSUMED", 1))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_request_and_target_conflicts_fail_closed(self):
        self.initialize()
        self.assertEqual(self.store.save_record(record(), 0).status, "SAVED")
        request_conflict = record(head_sha="c" * 40, ci_run_id=51)
        target_conflict = record(request_id="approval-pr-51")
        self.assertEqual(
            self.store.save_record(request_conflict, 1).reason_codes,
            ("REMOTE_APPROVAL_REQUEST_ID_CONFLICT",),
        )
        self.assertEqual(
            self.store.save_record(target_conflict, 1).reason_codes,
            ("REMOTE_APPROVAL_TARGET_CONFLICT",),
        )

    def test_invalid_record_does_not_mutate_store(self):
        self.initialize()
        before = self.store.path.read_bytes()
        result = self.store.save_record(record(extra=True), 0)
        self.assertEqual(result.status, "RECOVERY_BLOCKED")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_lock_and_temp_artifacts_are_not_forced_or_promoted(self):
        self.initialize()
        self.store.lock_path.write_bytes(b"existing")
        self.assertEqual(self.store.load().status, "LOCKED")
        self.assertEqual(self.store.save_record(record(), 0).status, "LOCKED")
        self.assertTrue(self.store.lock_path.exists())
        self.store.lock_path.unlink()
        self.store.temp_path.write_bytes(b"partial")
        before = self.store.path.read_bytes()
        self.assertEqual(self.store.load().status, "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(
            self.store.save_record(record(), 0).status,
            "MANUAL_REVIEW_REQUIRED",
        )
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_malformed_and_noncanonical_store_are_not_repaired(self):
        self.store.path.parent.mkdir(parents=True)
        for content in (b"{", b'{"persistence_version":"0.1",'
                       b'"records":[],"revision":0}\n'):
            self.store.path.write_bytes(content)
            self.assertEqual(self.store.load().status, "RECOVERY_BLOCKED")
            self.assertEqual(self.store.path.read_bytes(), content)

    def test_atomic_replace_requires_exact_read_back(self):
        self.initialize()
        current = self.store.load()
        blocked = persistence.ReplayLoadResult(
            "0.1", "RECOVERY_BLOCKED", None, None,
            ("FIXTURE_FAILURE",),
        )
        with mock.patch.object(
            persistence, "_decode", side_effect=(current, blocked),
        ):
            result = self.store.save_record(record(), 0)
        self.assertEqual(result.status, "RECOVERY_BLOCKED")
        self.assertFalse(self.store.temp_path.exists())

    def test_production_read_only_store_rejects_writes(self):
        read_only = persistence.RemoteApprovalReplayStore._for_read_only(
            self.root
        )
        self.assertEqual(
            read_only.initialize_for_test().status, "WRITE_DISABLED"
        )
        self.assertEqual(
            read_only.save_record(record(), 0).status, "WRITE_DISABLED"
        )

    def test_arbitrary_constructor_and_formal_test_root_are_rejected(self):
        with self.assertRaises(ValueError):
            persistence.RemoteApprovalReplayStore(self.root, object())
        with self.assertRaises(ValueError):
            persistence.RemoteApprovalReplayStore.for_test(
                persistence.FORMAL_REPO_ROOT
            )


if __name__ == "__main__":
    unittest.main()
