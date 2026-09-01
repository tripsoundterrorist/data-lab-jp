from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402
import development_remote_iphone_approval_observation as adapter  # noqa: E402


NOW = 2_000_000_000
CHECKPOINT = "a" * 64
SHA = "b" * 40


def awaiting_approval():
    return evidence_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=47,
        approval_status="REQUIRED",
    )


def observation(**changes):
    values = {
        "observation_version": adapter.OBSERVATION_VERSION,
        "source": adapter.APPROVED_SOURCE,
        "repository": adapter.APPROVED_REPOSITORY,
        "device_class": adapter.APPROVED_DEVICE_CLASS,
        "request_id": "approval-pr-47",
        "current_gate_id": "current-gate",
        "next_gate_id": "next-gate",
        "head_sha": SHA,
        "ci_run_id": 47,
        "status": "APPROVED",
        "requested_at_epoch_s": NOW - 60,
        "decided_at_epoch_s": NOW,
    }
    values.update(changes)
    return adapter.RemoteApprovalObservation(**values)


class DevelopmentRemoteIPhoneApprovalObservationTests(unittest.TestCase):
    def test_fresh_exact_approval_advances_coordinator_to_ready(self):
        bound = lambda value: adapter.observe(
            value, observation(), evaluated_at_epoch_s=NOW
        )
        result = coordinator.DevelopmentGateCoordinator._for_test({
            "REQUEST_APPROVAL": bound,
        }).coordinate(awaiting_approval())
        self.assertEqual(result.status, "ACTION_COMPLETED")
        self.assertEqual(result.after_status, "NEXT_GATE_READY")

    def test_pending_is_uncertain_without_updated_evidence(self):
        result = adapter.observe(
            awaiting_approval(),
            observation(status="PENDING", decided_at_epoch_s=None),
            evaluated_at_epoch_s=NOW,
        )
        self.assertEqual(result.status, coordinator.ACTION_UNCERTAIN)
        self.assertIsNone(result.evidence)

    def test_denied_fails_without_updated_evidence(self):
        result = adapter.observe(
            awaiting_approval(), observation(status="DENIED"),
            evaluated_at_epoch_s=NOW,
        )
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertEqual(result.reason_codes, ("REMOTE_APPROVAL_DENIED",))
        self.assertIsNone(result.evidence)

    def test_identity_is_exact(self):
        cases = (
            observation(source="CHAT_MESSAGE"),
            observation(repository="other/repo"),
            observation(device_class="IPAD"),
            observation(observation_version="9.9"),
            observation(request_id="invalid request"),
        )
        for item in cases:
            with self.subTest(item=item):
                result = adapter.observe(
                    awaiting_approval(), item, evaluated_at_epoch_s=NOW
                )
                self.assertEqual(
                    result.reason_codes,
                    ("REMOTE_APPROVAL_IDENTITY_INVALID",),
                )

    def test_gate_sha_and_ci_target_must_all_match(self):
        cases = (
            observation(current_gate_id="other-gate"),
            observation(next_gate_id="other-gate"),
            observation(head_sha="c" * 40),
            observation(ci_run_id=48),
        )
        for item in cases:
            with self.subTest(item=item):
                result = adapter.observe(
                    awaiting_approval(), item, evaluated_at_epoch_s=NOW
                )
                self.assertEqual(
                    result.reason_codes,
                    ("REMOTE_APPROVAL_TARGET_MISMATCH",),
                )

    def test_stale_decision_fails_closed(self):
        item = observation(
            requested_at_epoch_s=NOW - adapter.MAX_DECISION_AGE_SECONDS - 2,
            decided_at_epoch_s=NOW - adapter.MAX_DECISION_AGE_SECONDS - 1,
        )
        result = adapter.observe(
            awaiting_approval(), item, evaluated_at_epoch_s=NOW
        )
        self.assertEqual(result.reason_codes, ("REMOTE_APPROVAL_STALE",))

    def test_exact_maximum_decision_age_is_accepted(self):
        item = observation(
            requested_at_epoch_s=NOW - adapter.MAX_DECISION_AGE_SECONDS - 1,
            decided_at_epoch_s=NOW - adapter.MAX_DECISION_AGE_SECONDS,
        )
        result = adapter.observe(
            awaiting_approval(), item, evaluated_at_epoch_s=NOW
        )
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)

    def test_invalid_and_future_timestamps_fail_closed(self):
        cases = (
            (observation(requested_at_epoch_s=True), NOW),
            (observation(
                status="PENDING", requested_at_epoch_s=NOW + 1,
                decided_at_epoch_s=None,
            ), NOW),
            (observation(decided_at_epoch_s=NOW - 61), NOW),
            (observation(decided_at_epoch_s=NOW + 1), NOW),
            (observation(), True),
            (observation(status="PENDING"), NOW),
        )
        for item, evaluated in cases:
            with self.subTest(item=item, evaluated=evaluated):
                result = adapter.observe(
                    awaiting_approval(), item,
                    evaluated_at_epoch_s=evaluated,
                )
                self.assertEqual(
                    result.reason_codes,
                    ("REMOTE_APPROVAL_TIMESTAMP_INVALID",),
                )

    def test_unknown_status_fails_closed(self):
        result = adapter.observe(
            awaiting_approval(), observation(status="approved"),
            evaluated_at_epoch_s=NOW,
        )
        self.assertEqual(
            result.reason_codes, ("REMOTE_APPROVAL_STATUS_INVALID",)
        )

    def test_observation_is_only_accepted_at_approval_stage(self):
        incomplete = evidence_core.DevelopmentGateEvidence(
            "current-gate", "next-gate"
        )
        result = adapter.observe(
            incomplete, observation(), evaluated_at_epoch_s=NOW
        )
        self.assertEqual(
            result.reason_codes, ("REMOTE_APPROVAL_NOT_EXPECTED",)
        )

    def test_adapter_reads_no_clock_network_or_filesystem(self):
        with (mock.patch("time.time", side_effect=AssertionError),
              mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            result = adapter.observe(
                awaiting_approval(), observation(),
                evaluated_at_epoch_s=NOW,
            )
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
