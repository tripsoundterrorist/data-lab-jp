from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402
import development_test_result_observation as observation  # noqa: E402


CHECKPOINT_REF = "a" * 64


def evidence(**changes):
    value = evidence_core.DevelopmentGateEvidence(
        current_gate_id="current-gate",
        next_gate_id="next-gate",
        checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT_REF,
    )
    return replace(value, **changes)


def observed(**changes):
    values = {
        "observation_version": observation.OBSERVATION_VERSION,
        "source": observation.SOURCE,
        "checkpoint_ref": CHECKPOINT_REF,
        "test_tier": "FAST",
        "status": "COMPLETED",
        "conclusion": "PASSED",
        "test_count": 300,
        "skipped_count": 0,
        "failure_count": 0,
        "error_count": 0,
    }
    values.update(changes)
    return observation.TestResultObservation(**values)


class DevelopmentTestResultObservationTests(unittest.TestCase):
    def test_passed_result_advances_only_to_commit_push_required(self):
        before = evidence()
        result = observation.observe(before, observed())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        self.assertEqual(result.action, "RUN_TESTS")
        self.assertEqual(result.evidence.test_tier, "FAST")
        self.assertEqual(result.evidence.test_status, "PASSED")
        self.assertEqual(
            evidence_core.evaluate(result.evidence).status,
            "COMMIT_PUSH_REQUIRED",
        )
        self.assertEqual(before, evidence())

    def test_each_supported_tier_is_preserved_exactly(self):
        for tier in ("FAST", "REGRESSION", "FULL"):
            with self.subTest(tier=tier):
                result = observation.observe(
                    evidence(), observed(test_tier=tier)
                )
                self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
                self.assertEqual(result.evidence.test_tier, tier)

    def test_coordinator_revalidates_exact_progress(self):
        adapter = lambda current: observation.observe(current, observed())
        result = coordinator.DevelopmentGateCoordinator._for_test({
            "RUN_TESTS": adapter,
        }).coordinate(evidence())
        self.assertEqual(result.status, "ACTION_COMPLETED")
        self.assertEqual(result.before_status, "TEST_REQUIRED")
        self.assertEqual(result.after_status, "COMMIT_PUSH_REQUIRED")
        self.assertFalse(result.next_gate_started)

    def test_queued_and_in_progress_are_uncertain_without_evidence(self):
        for status in ("QUEUED", "IN_PROGRESS"):
            with self.subTest(status=status):
                result = observation.observe(
                    evidence(), observed(status=status, conclusion=None)
                )
                self.assertEqual(result.status, coordinator.ACTION_UNCERTAIN)
                self.assertIsNone(result.evidence)

    def test_failed_result_never_advances(self):
        result = observation.observe(evidence(), observed(
            conclusion="FAILED", failure_count=1,
        ))
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertIsNone(result.evidence)
        self.assertEqual(result.reason_codes, ("TEST_RUN_FAILED",))

    def test_checkpoint_binding_and_order_are_exact(self):
        cases = (
            observed(checkpoint_ref="b" * 64),
            observed(checkpoint_ref="A" * 64),
            observed(checkpoint_ref="a" * 63),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)
        result = observation.observe(
            evidence(test_tier="FAST", test_status="PASSED"), observed()
        )
        self.assertEqual(result.status, coordinator.ACTION_FAILED)

    def test_malformed_and_contradictory_results_fail_closed(self):
        cases = (
            object(),
            observed(observation_version="9.9"),
            observed(source="UNKNOWN"),
            observed(test_tier="SMOKE"),
            observed(status="UNKNOWN"),
            observed(test_count=True),
            observed(test_count=0),
            observed(skipped_count=-1),
            observed(skipped_count=301),
            observed(failure_count=301),
            observed(skipped_count=300, failure_count=1),
            observed(status="IN_PROGRESS", conclusion=None, failure_count=1),
            observed(conclusion="PASSED", failure_count=1),
            observed(conclusion="FAILED"),
            observed(conclusion=None),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_observer_exposes_no_execution_or_external_action(self):
        result = observation.observe(evidence(), observed())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        for name in (
            "run", "run_tests", "subprocess", "commit", "push",
            "wait_for_ci", "start_next_gate", "activate_live",
        ):
            self.assertFalse(hasattr(observation, name))


if __name__ == "__main__":
    unittest.main()
