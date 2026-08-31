from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_ci_observation as adapter  # noqa: E402
import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40


def awaiting_ci(**changes):
    base = evidence.DevelopmentGateEvidence(
        "gate-a", "gate-b", checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT, test_tier="FULL", test_status="PASSED",
        commit_sha=SHA, pushed_sha=SHA,
    )
    return replace(base, **changes)


def observation(**changes):
    base = adapter.CIObservation(
        adapter.OBSERVATION_VERSION, "GITHUB_ACTIONS",
        adapter.APPROVED_REPOSITORY, adapter.APPROVED_WORKFLOW,
        "pull_request", "completed", "success", SHA, 33352559792,
        (
            adapter.CIJobObservation("fast", "completed", "success", "FAST"),
            adapter.CIJobObservation(
                "validation", "completed", "success", "REGRESSION"
            ),
        ),
    )
    return replace(base, **changes)


class DevelopmentGateCIObservationTests(unittest.TestCase):
    def test_pull_request_success_advances_to_ready(self):
        result = adapter.observe(awaiting_ci(), observation(), approval_required=False)
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        self.assertEqual(evidence.evaluate(result.evidence).status, "NEXT_GATE_READY")

    def test_push_success_requires_full_tier(self):
        jobs = (
            adapter.CIJobObservation("fast", "completed", "success", "FAST"),
            adapter.CIJobObservation("validation", "completed", "success", "FULL"),
        )
        result = adapter.observe(
            awaiting_ci(), observation(event="push", jobs=jobs),
            approval_required=True,
        )
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)
        self.assertEqual(evidence.evaluate(result.evidence).status, "APPROVAL_REQUIRED")

    def test_incomplete_is_uncertain_without_updated_evidence(self):
        result = adapter.observe(
            awaiting_ci(), observation(status="in_progress", conclusion=None),
            approval_required=False,
        )
        self.assertEqual(result.status, coordinator.ACTION_UNCERTAIN)
        self.assertIsNone(result.evidence)

    def test_failed_ci_is_failed_safe(self):
        result = adapter.observe(
            awaiting_ci(), observation(conclusion="failure"),
            approval_required=False,
        )
        self.assertEqual(result.status, coordinator.ACTION_FAILED)

    def test_identity_sha_and_tier_fail_closed(self):
        cases = (
            observation(repository="other/repo"),
            observation(workflow_name="Deploy"),
            observation(head_sha="c" * 40),
            observation(run_id=True),
            observation(event="schedule"),
            observation(jobs=(
                adapter.CIJobObservation("fast", "completed", "success", "FAST"),
                adapter.CIJobObservation("validation", "completed", "success", "FULL"),
            )),
            observation(jobs=(
                adapter.CIJobObservation("fast", "completed", "failure", "FAST"),
                adapter.CIJobObservation(
                    "validation", "completed", "success", "REGRESSION"
                ),
            )),
        )
        for item in cases:
            with self.subTest(item=item):
                result = adapter.observe(awaiting_ci(), item, approval_required=False)
                self.assertEqual(result.status, coordinator.ACTION_FAILED)
                self.assertIsNone(result.evidence)

    def test_observation_only_allowed_at_ci_stage(self):
        result = adapter.observe(
            evidence.DevelopmentGateEvidence("gate-a", "gate-b"), observation(),
            approval_required=False,
        )
        self.assertEqual(result.reason_codes, ("CI_OBSERVATION_NOT_EXPECTED",))

    def test_coordinator_revalidates_adapter_output(self):
        bound = lambda value: adapter.observe(
            value, observation(), approval_required=False
        )
        result = coordinator.DevelopmentGateCoordinator._for_test(
            {"WAIT_FOR_CI": bound}
        ).coordinate(awaiting_ci())
        self.assertEqual((result.status, result.after_status),
                         ("ACTION_COMPLETED", "NEXT_GATE_READY"))

    def test_no_io_or_polling(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            result = adapter.observe(
                awaiting_ci(), observation(), approval_required=False
            )
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
