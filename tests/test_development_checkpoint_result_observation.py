from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_checkpoint_result_observation as observation  # noqa: E402
import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402
import unattended_checkpoint_storage as checkpoint_storage  # noqa: E402


CHECKPOINT_REF = "a" * 64


def evidence(**changes):
    value = evidence_core.DevelopmentGateEvidence(
        current_gate_id="current-gate",
        next_gate_id="next-gate",
    )
    return replace(value, **changes)


def saved(status="SAVED", **changes):
    values = {
        "result_version": checkpoint_storage.CHECKPOINT_RESULT_VERSION,
        "status": status,
        "checkpoint_storage_id": CHECKPOINT_REF,
        "reason_codes": (
            "CHECKPOINT_STORED" if status == "SAVED"
            else "CHECKPOINT_ALREADY_STORED",
        ),
    }
    values.update(changes)
    return checkpoint_storage.CheckpointSaveResult(**values)


class DevelopmentCheckpointResultObservationTests(unittest.TestCase):
    def test_saved_result_advances_only_to_test_required(self):
        before = evidence()
        result = observation.observe(before, saved())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        self.assertEqual(result.action, "SAVE_CHECKPOINT")
        self.assertEqual(
            evidence_core.evaluate(result.evidence).status,
            "TEST_REQUIRED",
        )
        self.assertEqual(result.evidence.checkpoint_status, "SAVED")
        self.assertEqual(result.evidence.checkpoint_ref, CHECKPOINT_REF)
        self.assertEqual(before, evidence())

    def test_idempotent_no_change_is_durable(self):
        result = observation.observe(evidence(), saved("NO_CHANGE"))
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        self.assertEqual(result.evidence.checkpoint_status, "NO_CHANGE")
        self.assertEqual(
            evidence_core.evaluate(result.evidence).next_action,
            "RUN_TESTS",
        )

    def test_coordinator_revalidates_exact_progress(self):
        adapter = lambda current: observation.observe(current, saved())
        result = coordinator.DevelopmentGateCoordinator._for_test({
            "SAVE_CHECKPOINT": adapter,
        }).coordinate(evidence())
        self.assertEqual(result.status, "ACTION_COMPLETED")
        self.assertEqual(result.before_status, "CHECKPOINT_REQUIRED")
        self.assertEqual(result.after_status, "TEST_REQUIRED")
        self.assertFalse(result.next_gate_started)

    def test_observation_is_rejected_when_checkpoint_is_not_expected(self):
        result = observation.observe(
            evidence(checkpoint_status="SAVED", checkpoint_ref=CHECKPOINT_REF),
            saved(),
        )
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertIsNone(result.evidence)

    def test_uncertain_and_failed_save_results_never_advance(self):
        cases = (
            saved(
                "WRITE_DISABLED", checkpoint_storage_id=None,
                reason_codes=("PRODUCTION_CHECKPOINT_WRITE_DISABLED",),
            ),
            saved(
                "RECOVERY_BLOCKED", checkpoint_storage_id=None,
                reason_codes=("CHECKPOINT_INVALID",),
            ),
            saved(
                "MANUAL_REVIEW_REQUIRED", checkpoint_storage_id=None,
                reason_codes=("CHECKPOINT_TEMP_ARTIFACT_PRESENT",),
            ),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_malformed_success_result_fails_closed(self):
        cases = (
            object(),
            saved(result_version="9.9"),
            saved(checkpoint_storage_id="A" * 64),
            saved(checkpoint_storage_id="a" * 63),
            saved(reason_codes=("CHECKPOINT_ALREADY_STORED",)),
            saved("NO_CHANGE", reason_codes=("CHECKPOINT_STORED",)),
            saved(reason_codes=("CHECKPOINT_STORED", "EXTRA")),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_observer_performs_no_storage_or_external_action(self):
        with mock.patch.object(
            checkpoint_storage.CheckpointStorage,
            "save_checkpoint",
            side_effect=AssertionError("write attempted"),
        ), mock.patch.object(
            checkpoint_storage.CheckpointStorage,
            "load_checkpoint",
            side_effect=AssertionError("read attempted"),
        ):
            result = observation.observe(evidence(), saved())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        for name in (
            "save_checkpoint", "load_checkpoint", "run_tests", "commit",
            "push", "wait_for_ci", "start_next_gate",
        ):
            self.assertFalse(hasattr(observation, name))


if __name__ == "__main__":
    unittest.main()
