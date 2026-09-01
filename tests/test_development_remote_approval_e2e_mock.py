from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_evidence as evidence_core  # noqa: E402
import development_remote_approval_e2e_mock as integration  # noqa: E402
import development_remote_approval_replay_persistence as persistence  # noqa: E402
import development_remote_iphone_approval_observation as approval  # noqa: E402


NOW = 2_000_000_000
SHA = "a" * 40


def evidence():
    return evidence_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref="b" * 64, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=54,
        approval_status="REQUIRED",
    )


def observation(**changes):
    values = {
        "observation_version": approval.OBSERVATION_VERSION,
        "source": approval.APPROVED_SOURCE,
        "repository": approval.APPROVED_REPOSITORY,
        "device_class": approval.APPROVED_DEVICE_CLASS,
        "request_id": "approval-pr-54",
        "current_gate_id": "current-gate",
        "next_gate_id": "next-gate",
        "head_sha": SHA,
        "ci_run_id": 54,
        "status": "APPROVED",
        "requested_at_epoch_s": NOW - 60,
        "decided_at_epoch_s": NOW,
    }
    values.update(changes)
    return approval.RemoteApprovalObservation(**values)


class RemoteApprovalE2EMockIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="approval-e2e-")
        self.addCleanup(self.temporary.cleanup)
        self.store = persistence.RemoteApprovalReplayStore.for_test(
            Path(self.temporary.name).resolve()
        )
        self.assertEqual(self.store.initialize_for_test().status, "SAVED")
        self.integration = integration.RemoteApprovalE2EMockIntegration._for_test(
            self.store
        )

    def execute(self, **changes):
        values = {
            "evidence": evidence(), "observation": observation(),
            "evaluated_at_epoch_s": NOW, "expected_revision": 0,
        }
        values.update(changes)
        return self.integration.run(**values)

    def test_real_components_complete_once_and_persist_once(self):
        original_load = self.store.load
        original_save = self.store.save_record
        with (mock.patch.object(
                  self.store, "load", wraps=original_load
              ) as load,
              mock.patch.object(
                  self.store, "save_record", wraps=original_save
              ) as save):
            result = self.execute()
        self.assertEqual(result.status, "MOCK_APPROVAL_FLOW_COMPLETED")
        self.assertTrue(result.approval_action_invoked)
        self.assertTrue(result.next_gate_ready)
        self.assertFalse(result.next_gate_started)
        load.assert_called_once_with()
        save.assert_called_once()

        persisted = self.store.load()
        self.assertEqual((persisted.revision, len(persisted.records)), (1, 1))

    def test_replay_is_blocked_without_second_save(self):
        self.assertEqual(self.execute().status, "MOCK_APPROVAL_FLOW_COMPLETED")
        before = self.store.path.read_bytes()
        with mock.patch.object(
            self.store, "save_record", side_effect=AssertionError
        ) as save:
            result = self.execute(expected_revision=1)
        self.assertEqual(result.status, "MOCK_APPROVAL_FLOW_BLOCKED")
        self.assertFalse(result.next_gate_ready)
        self.assertFalse(result.next_gate_started)
        self.assertEqual(self.store.path.read_bytes(), before)
        save.assert_not_called()

    def test_stale_revision_is_blocked_without_save_or_retry(self):
        with mock.patch.object(
            self.store, "save_record", side_effect=AssertionError
        ) as save:
            result = self.execute(expected_revision=1)
        self.assertEqual(result.status, "MOCK_APPROVAL_FLOW_BLOCKED")
        self.assertTrue(result.approval_action_invoked)
        self.assertFalse(result.next_gate_ready)
        save.assert_not_called()

    def test_pending_is_uncertain_and_denied_is_blocked_without_save(self):
        cases = (
            (observation(status="PENDING", decided_at_epoch_s=None),
             "MOCK_APPROVAL_FLOW_UNCERTAIN"),
            (observation(status="DENIED"), "MOCK_APPROVAL_FLOW_BLOCKED"),
        )
        for observed, expected in cases:
            with self.subTest(expected=expected), mock.patch.object(
                self.store, "save_record", side_effect=AssertionError
            ) as save:
                result = self.execute(observation=observed)
                self.assertEqual(result.status, expected)
                self.assertFalse(result.next_gate_ready)
                save.assert_not_called()

    def test_uncertain_persistence_never_releases_next_gate(self):
        blocked = persistence.ReplaySaveResult(
            "0.1", "RECOVERY_BLOCKED", None, ("READ_BACK_FAILED",)
        )
        with mock.patch.object(
            self.store, "save_record", return_value=blocked
        ) as save:
            result = self.execute()
        self.assertEqual(result.status, "MOCK_APPROVAL_FLOW_UNCERTAIN")
        self.assertFalse(result.next_gate_ready)
        self.assertFalse(result.next_gate_started)
        save.assert_called_once()

    def test_invalid_gate_stage_is_blocked_before_store_io(self):
        invalid = evidence_core.DevelopmentGateEvidence(
            "current-gate", "next-gate"
        )
        with (mock.patch.object(
                  self.store, "load", side_effect=AssertionError
              ) as load,
              mock.patch.object(
                  self.store, "save_record", side_effect=AssertionError
              ) as save):
            result = self.execute(evidence=invalid)
        self.assertEqual(result.status, "MOCK_APPROVAL_FLOW_BLOCKED")
        self.assertFalse(result.approval_action_invoked)
        load.assert_not_called()
        save.assert_not_called()

    def test_disabled_integration_performs_no_io(self):
        fake = mock.Mock()
        disabled = integration.RemoteApprovalE2EMockIntegration(fake)
        result = disabled.run(
            evidence(), observation(), evaluated_at_epoch_s=NOW,
            expected_revision=0,
        )
        self.assertEqual(result.status, "AUTOMATION_DISABLED")
        self.assertFalse(result.approval_action_invoked)
        self.assertFalse(result.next_gate_ready)
        self.assertFalse(result.next_gate_started)
        fake.assert_not_called()

    def test_no_production_or_live_activation_surface(self):
        cls = integration.RemoteApprovalE2EMockIntegration
        self.assertFalse(hasattr(cls, "for_production"))
        self.assertFalse(hasattr(cls, "for_live"))
        self.assertFalse(hasattr(integration, "activate_production"))


if __name__ == "__main__":
    unittest.main()
