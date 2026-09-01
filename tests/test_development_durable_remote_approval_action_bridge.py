from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_durable_remote_approval_action_bridge as bridge  # noqa: E402
import development_gate_coordinator as gate_coordinator  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402
import development_remote_approval_durable_coordinator as durable  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40


def awaiting_approval():
    return evidence_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=53,
        approval_status="REQUIRED",
    )


def result(status="REMOTE_APPROVAL_APPLIED_DURABLY", **changes):
    values = {
        "coordinator_version": durable.COORDINATOR_VERSION,
        "status": status,
        "evidence": replace(awaiting_approval(), approval_status="APPROVED"),
        "durable": True,
        "replay_blocked": False,
        "reason_codes": ("REMOTE_APPROVAL_RECORDED_DURABLY",),
    }
    if status != "REMOTE_APPROVAL_APPLIED_DURABLY":
        values.update(
            evidence=None, durable=False,
            replay_blocked=status == "APPROVAL_REPLAY_BLOCKED",
            reason_codes=("FIXTURE_REASON",),
        )
    values.update(changes)
    return durable.DurableRemoteApprovalResult(**values)


class Coordinator:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def coordinate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.value


def enabled(value):
    coordinator = Coordinator(value)
    adapter = bridge.DurableRemoteApprovalActionBridge._for_test(
        coordinator, "observation", evaluated_at_epoch_s=2_000_000_000,
        expected_revision=4,
    )
    return coordinator, adapter


class DurableRemoteApprovalActionBridgeTests(unittest.TestCase):
    def test_exact_durable_result_advances_existing_gate_coordinator(self):
        downstream, adapter = enabled(result())
        actual = gate_coordinator.DevelopmentGateCoordinator._for_test({
            "REQUEST_APPROVAL": adapter,
        }).coordinate(awaiting_approval())
        self.assertEqual(
            (actual.status, actual.after_status),
            ("ACTION_COMPLETED", "NEXT_GATE_READY"),
        )
        self.assertEqual(len(downstream.calls), 1)
        args, kwargs = downstream.calls[0]
        self.assertEqual(args, (awaiting_approval(), "observation"))
        self.assertEqual(kwargs, {
            "evaluated_at_epoch_s": 2_000_000_000,
            "expected_revision": 4,
        })

    def test_uncertain_result_remains_uncertain_without_evidence(self):
        downstream, adapter = enabled(result("REMOTE_APPROVAL_UNCERTAIN"))
        action = adapter(awaiting_approval())
        self.assertEqual(action.status, gate_coordinator.ACTION_UNCERTAIN)
        self.assertIsNone(action.evidence)
        self.assertEqual(len(downstream.calls), 1)

    def test_conflict_replay_rejection_and_recovery_block_fail(self):
        statuses = (
            "APPROVAL_CONFLICT", "APPROVAL_REPLAY_BLOCKED",
            "REMOTE_APPROVAL_REJECTED", "RECOVERY_BLOCKED",
            "AUTOMATION_DISABLED",
        )
        for status in statuses:
            with self.subTest(status=status):
                downstream, adapter = enabled(result(status))
                action = adapter(awaiting_approval())
                self.assertEqual(action.status, gate_coordinator.ACTION_FAILED)
                self.assertIsNone(action.evidence)
                self.assertEqual(len(downstream.calls), 1)

    def test_non_durable_success_and_nonempty_failed_evidence_are_invalid(self):
        cases = (
            result(durable=False),
            result(replay_blocked=True),
            result(evidence=awaiting_approval()),
            result("APPROVAL_CONFLICT", evidence=awaiting_approval()),
            result("APPROVAL_CONFLICT", durable=True),
            result("APPROVAL_CONFLICT", replay_blocked=True),
        )
        for value in cases:
            with self.subTest(value=value):
                _, adapter = enabled(value)
                action = adapter(awaiting_approval())
                self.assertEqual(
                    action.reason_codes,
                    ("DURABLE_REMOTE_APPROVAL_RESULT_INVALID",),
                )
                self.assertIsNone(action.evidence)

    def test_unknown_version_status_or_reason_is_invalid(self):
        cases = (
            result(coordinator_version="9.9"),
            result("UNKNOWN", evidence=None, durable=False),
            result(reason_codes=()),
            result(reason_codes=("unsafe reason",)),
            object(),
        )
        for value in cases:
            with self.subTest(value=value):
                _, adapter = enabled(value)
                action = adapter(awaiting_approval())
                self.assertEqual(
                    action.reason_codes,
                    ("DURABLE_REMOTE_APPROVAL_RESULT_INVALID",),
                )

    def test_disabled_bridge_and_exception_invoke_no_fallback(self):
        disabled = bridge.DurableRemoteApprovalActionBridge.disabled()
        action = disabled(awaiting_approval())
        self.assertEqual(action.status, gate_coordinator.ACTION_FAILED)
        self.assertEqual(
            action.reason_codes,
            ("DURABLE_REMOTE_APPROVAL_BRIDGE_DISABLED",),
        )

        downstream = mock.Mock()
        downstream.coordinate.side_effect = RuntimeError("fixture-secret")
        adapter = bridge.DurableRemoteApprovalActionBridge._for_test(
            downstream, "observation", evaluated_at_epoch_s=1,
            expected_revision=0,
        )
        uncertain = adapter(awaiting_approval())
        self.assertEqual(uncertain.status, gate_coordinator.ACTION_UNCERTAIN)
        self.assertEqual(
            uncertain.reason_codes,
            ("DURABLE_REMOTE_APPROVAL_COORDINATOR_EXCEPTION",),
        )
        downstream.coordinate.assert_called_once()

    def test_no_production_activation_factory(self):
        self.assertFalse(
            hasattr(bridge.DurableRemoteApprovalActionBridge, "for_production")
        )
        self.assertFalse(hasattr(bridge, "activate_production"))


if __name__ == "__main__":
    unittest.main()
