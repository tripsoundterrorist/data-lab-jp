from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_commit_push_result_observation as observation  # noqa: E402
import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402


CHECKPOINT_REF = "a" * 64
COMMIT_SHA = "b" * 40


def evidence(**changes):
    value = evidence_core.DevelopmentGateEvidence(
        current_gate_id="current-gate",
        next_gate_id="next-gate",
        checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT_REF,
        test_tier="FAST",
        test_status="PASSED",
    )
    return replace(value, **changes)


def observed(**changes):
    values = {
        "observation_version": observation.OBSERVATION_VERSION,
        "source": observation.SOURCE,
        "repository": observation.APPROVED_REPOSITORY,
        "remote": observation.APPROVED_REMOTE,
        "branch": "codex/current-gate",
        "base_branch": observation.APPROVED_BASE,
        "checkpoint_ref": CHECKPOINT_REF,
        "test_tier": "FAST",
        "status": "COMPLETED",
        "conclusion": "PUSHED",
        "commit_sha": COMMIT_SHA,
        "pushed_sha": COMMIT_SHA,
        "force_push": False,
    }
    values.update(changes)
    return observation.CommitPushObservation(**values)


class DevelopmentCommitPushResultObservationTests(unittest.TestCase):
    def test_pushed_result_advances_only_to_ci_required(self):
        before = evidence()
        result = observation.observe(before, observed())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        self.assertEqual(result.action, "COMMIT_AND_PUSH")
        self.assertEqual(result.evidence.commit_sha, COMMIT_SHA)
        self.assertEqual(result.evidence.pushed_sha, COMMIT_SHA)
        self.assertEqual(
            evidence_core.evaluate(result.evidence).status,
            "CI_REQUIRED",
        )
        self.assertEqual(before, evidence())

    def test_coordinator_revalidates_exact_progress(self):
        adapter = lambda current: observation.observe(current, observed())
        result = coordinator.DevelopmentGateCoordinator._for_test({
            "COMMIT_AND_PUSH": adapter,
        }).coordinate(evidence())
        self.assertEqual(result.status, "ACTION_COMPLETED")
        self.assertEqual(result.before_status, "COMMIT_PUSH_REQUIRED")
        self.assertEqual(result.after_status, "CI_REQUIRED")
        self.assertFalse(result.next_gate_started)

    def test_queued_and_in_progress_are_uncertain_without_evidence(self):
        for status in ("QUEUED", "IN_PROGRESS"):
            with self.subTest(status=status):
                result = observation.observe(evidence(), observed(
                    status=status, conclusion=None,
                    commit_sha=None, pushed_sha=None,
                ))
                self.assertEqual(result.status, coordinator.ACTION_UNCERTAIN)
                self.assertIsNone(result.evidence)

    def test_failed_result_never_advances(self):
        result = observation.observe(evidence(), observed(
            conclusion="FAILED", pushed_sha=None,
        ))
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertIsNone(result.evidence)
        self.assertEqual(result.reason_codes, ("COMMIT_PUSH_FAILED",))

    def test_exact_repository_remote_base_and_branch_are_required(self):
        cases = (
            observed(repository="other/repository"),
            observed(remote="upstream"),
            observed(base_branch="develop"),
            observed(branch="main"),
            observed(branch="codex/Bad"),
            observed(branch="codex/a..b"),
            observed(branch="codex/a//b"),
            observed(branch="codex/a/"),
            observed(branch="codex/.hidden"),
            observed(branch="codex/a.lock"),
            observed(branch="codex/a.lock/b"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_checkpoint_test_and_stage_binding_are_exact(self):
        cases = (
            observed(checkpoint_ref="c" * 64),
            observed(test_tier="REGRESSION"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)
        result = observation.observe(
            evidence(commit_sha=COMMIT_SHA, pushed_sha=COMMIT_SHA), observed()
        )
        self.assertEqual(result.status, coordinator.ACTION_FAILED)

    def test_sha_and_force_push_fail_closed(self):
        cases = (
            observed(commit_sha="B" * 40, pushed_sha="B" * 40),
            observed(commit_sha="b" * 39, pushed_sha="b" * 39),
            observed(pushed_sha="c" * 40),
            observed(force_push=True),
            observed(force_push=1),
            observed(conclusion="FAILED", pushed_sha=COMMIT_SHA),
            observed(conclusion="FAILED", commit_sha="invalid", pushed_sha=None),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_malformed_and_contradictory_results_fail_closed(self):
        cases = (
            object(),
            observed(observation_version="9.9"),
            observed(source="UNKNOWN"),
            observed(status="UNKNOWN"),
            observed(conclusion=None),
            observed(status="IN_PROGRESS", conclusion=None,
                     commit_sha="invalid", pushed_sha=None),
            observed(status="IN_PROGRESS", conclusion=None,
                     pushed_sha=COMMIT_SHA),
        )
        for value in cases:
            with self.subTest(value=value):
                result = observation.observe(evidence(), value)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_observer_exposes_no_git_or_external_action(self):
        result = observation.observe(evidence(), observed())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        for name in (
            "commit", "push", "force_push", "merge", "subprocess",
            "github", "wait_for_ci", "start_next_gate", "activate_live",
        ):
            self.assertFalse(hasattr(observation, name))


if __name__ == "__main__":
    unittest.main()
