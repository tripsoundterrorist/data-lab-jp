from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_evidence as evidence_core  # noqa: E402
import development_remote_approval_durable_coordinator as durable  # noqa: E402
import development_remote_approval_replay_persistence as persistence  # noqa: E402
import development_remote_iphone_approval_observation as approval  # noqa: E402


NOW = 2_000_000_000
SHA = "a" * 40


def evidence():
    return evidence_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref="b" * 64, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=52,
        approval_status="REQUIRED",
    )


def observation(**changes):
    values = {
        "observation_version": approval.OBSERVATION_VERSION,
        "source": approval.APPROVED_SOURCE,
        "repository": approval.APPROVED_REPOSITORY,
        "device_class": approval.APPROVED_DEVICE_CLASS,
        "request_id": "approval-pr-52",
        "current_gate_id": "current-gate",
        "next_gate_id": "next-gate",
        "head_sha": SHA,
        "ci_run_id": 52,
        "status": "APPROVED",
        "requested_at_epoch_s": NOW - 60,
        "decided_at_epoch_s": NOW,
    }
    values.update(changes)
    return approval.RemoteApprovalObservation(**values)


class DurableRemoteApprovalCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="approval-durable-")
        self.addCleanup(self.temporary.cleanup)
        self.store = persistence.RemoteApprovalReplayStore.for_test(
            Path(self.temporary.name).resolve()
        )
        self.assertEqual(self.store.initialize_for_test().status, "SAVED")

    def coordinate(self, **changes):
        values = {
            "evidence": evidence(), "observation": observation(),
            "evaluated_at_epoch_s": NOW, "expected_revision": 0,
        }
        values.update(changes)
        return durable.DurableRemoteApprovalCoordinator._for_test(
            self.store
        ).coordinate(**values)

    def test_saved_is_the_durable_point_without_second_load(self):
        original_load = self.store.load
        original_save = self.store.save_record
        with (mock.patch.object(
                  self.store, "load", wraps=original_load
              ) as load,
              mock.patch.object(
                  self.store, "save_record", wraps=original_save
              ) as save):
            result = self.coordinate()
        self.assertEqual(result.status, "REMOTE_APPROVAL_APPLIED_DURABLY")
        self.assertTrue(result.durable)
        self.assertEqual(result.evidence.approval_status, "APPROVED")
        load.assert_called_once_with()
        save.assert_called_once()

    def test_replay_is_blocked_before_observation_or_save(self):
        first = self.coordinate()
        self.assertTrue(first.durable)
        observer = mock.Mock(side_effect=AssertionError)
        coordinator = durable.DurableRemoteApprovalCoordinator._for_test(
            self.store, observer
        )
        with mock.patch.object(
            self.store, "save_record", side_effect=AssertionError
        ):
            result = coordinator.coordinate(
                evidence(), observation(), evaluated_at_epoch_s=NOW,
                expected_revision=1,
            )
        self.assertEqual(result.status, "APPROVAL_REPLAY_BLOCKED")
        self.assertTrue(result.replay_blocked)
        self.assertFalse(result.durable)
        self.assertIsNone(result.evidence)
        observer.assert_not_called()

    def test_stale_revision_is_conflict_without_retry(self):
        observer = mock.Mock(side_effect=AssertionError)
        coordinator = durable.DurableRemoteApprovalCoordinator._for_test(
            self.store, observer
        )
        with mock.patch.object(
            self.store, "save_record", side_effect=AssertionError
        ):
            result = coordinator.coordinate(
                evidence(), observation(), evaluated_at_epoch_s=NOW,
                expected_revision=1,
            )
        self.assertEqual(result.status, "APPROVAL_CONFLICT")
        self.assertFalse(result.durable)
        self.assertIsNone(result.evidence)
        observer.assert_not_called()

    def test_save_race_stale_revision_is_not_retried(self):
        stale = persistence.ReplaySaveResult(
            "0.1", "STALE_REVISION", None, ("STALE_REVISION",)
        )
        with mock.patch.object(
            self.store, "save_record", return_value=stale
        ) as save:
            result = self.coordinate()
        self.assertEqual(result.status, "APPROVAL_CONFLICT")
        self.assertFalse(result.durable)
        self.assertIsNone(result.evidence)
        save.assert_called_once()

    def test_uncertain_save_withholds_evidence_and_does_not_retry(self):
        blocked = persistence.ReplaySaveResult(
            "0.1", "RECOVERY_BLOCKED", None, ("READ_BACK_FAILED",)
        )
        with (mock.patch.object(
                  self.store, "load", wraps=self.store.load
              ) as load,
              mock.patch.object(
                  self.store, "save_record", return_value=blocked
              ) as save):
            result = self.coordinate()
        self.assertEqual(result.status, "REMOTE_APPROVAL_UNCERTAIN")
        self.assertFalse(result.durable)
        self.assertIsNone(result.evidence)
        load.assert_called_once_with()
        save.assert_called_once()

    def test_pending_and_denied_never_save(self):
        cases = (
            (observation(status="PENDING", decided_at_epoch_s=None),
             "REMOTE_APPROVAL_UNCERTAIN"),
            (observation(status="DENIED"), "REMOTE_APPROVAL_REJECTED"),
        )
        for observed, expected in cases:
            with self.subTest(expected=expected), mock.patch.object(
                self.store, "save_record", side_effect=AssertionError
            ):
                result = self.coordinate(observation=observed)
                self.assertEqual(result.status, expected)
                self.assertFalse(result.durable)
                self.assertIsNone(result.evidence)

    def test_load_failure_and_disabled_coordinator_fail_closed(self):
        load = persistence.ReplayLoadResult(
            "0.1", "RECOVERY_BLOCKED", None, None, ("CORRUPT",)
        )
        with (mock.patch.object(self.store, "load", return_value=load),
              mock.patch.object(
                  self.store, "save_record", side_effect=AssertionError
              )):
            result = self.coordinate()
        self.assertEqual(result.status, "RECOVERY_BLOCKED")
        self.assertIsNone(result.evidence)

        disabled = durable.DurableRemoteApprovalCoordinator.disabled().coordinate(
            evidence(), observation(), evaluated_at_epoch_s=NOW,
            expected_revision=0,
        )
        self.assertEqual(disabled.status, "AUTOMATION_DISABLED")
        self.assertFalse(disabled.durable)

    def test_invalid_stage_and_revision_do_no_io(self):
        invalid = evidence_core.DevelopmentGateEvidence(
            "current-gate", "next-gate"
        )
        for supplied_evidence, revision in ((invalid, 0), (evidence(), True)):
            with self.subTest(revision=revision), mock.patch.object(
                self.store, "load", side_effect=AssertionError
            ):
                result = self.coordinate(
                    evidence=supplied_evidence, expected_revision=revision
                )
                self.assertEqual(result.status, "RECOVERY_BLOCKED")


if __name__ == "__main__":
    unittest.main()
