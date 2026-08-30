from dataclasses import asdict, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import unattended_job_queue as queue  # noqa: E402
from tests.test_unattended_job_queue import checkpoint, job  # noqa: E402


UTC = "2026-08-31T01:02:03.456789Z"


class ExecutionAdoptionTests(unittest.TestCase):
    def adopt(self, jobs=None, expected_job_id="job-a", **facts):
        return queue.adopt_ready_job_for_execution(
            [job()] if jobs is None else jobs, expected_job_id=expected_job_id,
            occurred_at=facts.pop("occurred_at", UTC), **facts)

    def test_version(self):
        self.assertEqual(queue.EXECUTION_ADOPTION_CONTRACT_VERSION, "0.1")

    def test_ready_zero_to_running_one(self):
        updated, result = self.adopt()
        self.assertEqual((updated.state, updated.attempt_count), (queue.RUNNING, 1))
        self.assertEqual((result.previous_state, result.new_state), (queue.READY, queue.RUNNING))

    def test_ready_one_to_running_two(self):
        updated, _ = self.adopt([job(attempt_count=1)])
        self.assertEqual(updated.attempt_count, 2)

    def test_max_minus_one_to_max(self):
        updated, _ = self.adopt([job(attempt_count=2, max_attempts=3)])
        self.assertEqual(updated.attempt_count, 3)

    def test_equal_max_rejected_without_mutation(self):
        original = job(attempt_count=3, max_attempts=3)
        before = asdict(original)
        updated, result = self.adopt([original])
        self.assertIsNone(updated)
        self.assertEqual(result.reason_code, "ATTEMPTS_EXHAUSTED")
        self.assertEqual(asdict(original), before)

    def test_above_max_is_invalid_contract(self):
        self.assertIn("MAX_ATTEMPTS_EXCEEDED", queue.validate_job(job(attempt_count=4))[1])
        self.assertEqual(self.adopt([job(attempt_count=4)])[1].reason_code,
                         "EXECUTION_ADOPTION_INVALID")

    def test_all_non_ready_states_rejected(self):
        for state in queue.JOB_STATES - {queue.READY}:
            value = job(state=state)
            if state == queue.CHECKPOINTED:
                value = replace(value, checkpoint_supported=True)
            with self.subTest(state=state):
                updated, result = self.adopt([value])
                self.assertIsNone(updated)
                self.assertEqual(result.reason_code, "EXECUTION_ADOPTION_INVALID")

    def test_approval_missing_and_satisfied(self):
        missing = job(requires_approval=True, risk_class=queue.APPROVAL_REQUIRED)
        self.assertEqual(self.adopt([missing])[1].reason_code, "SELECTION_CHANGED")
        approved = replace(missing, approval_received=True)
        self.assertEqual(self.adopt([approved])[0].state, queue.RUNNING)

    def test_prohibited_risk_rejected(self):
        self.assertIsNone(self.adopt([job(risk_class=queue.PROHIBITED_UNATTENDED)])[0])

    def test_external_read_requires_explicit_fact(self):
        value = job(risk_class=queue.EXTERNAL_READ)
        self.assertIsNone(self.adopt([value])[0])
        self.assertEqual(self.adopt([value], external_read_allowed=True)[0].state, queue.RUNNING)

    def test_dependency_incomplete_and_complete(self):
        jobs = [job("dep", state=queue.RUNNING), job("work", dependencies=("dep",))]
        self.assertIsNone(self.adopt(jobs, expected_job_id="work")[0])
        jobs[0] = replace(jobs[0], state=queue.DONE)
        self.assertEqual(self.adopt(jobs, expected_job_id="work")[0].state, queue.RUNNING)

    def test_blocker_rejected(self):
        self.assertIsNone(self.adopt([job(blocker_codes=("POLICY_BLOCK",))])[0])

    def test_window_fact_revalidated(self):
        value = job(deadline_class="TIME_WINDOW")
        self.assertIsNone(self.adopt([value], window_states={"job-a": "CLOSED"})[0])
        self.assertEqual(self.adopt([value], window_states={"job-a": "OPEN"})[0].state,
                         queue.RUNNING)

    def test_selection_changed(self):
        values = [job("old", priority="P2"), job("new", priority="P0")]
        updated, result = self.adopt(values, expected_job_id="old")
        self.assertIsNone(updated)
        self.assertEqual(result.reason_code, "SELECTION_CHANGED")

    def test_obsolete_expected_job(self):
        self.assertEqual(self.adopt([job("current")], expected_job_id="gone")[1].reason_code,
                         "OBSOLETE_SELECTION")

    def test_original_immutable_and_only_two_fields_change(self):
        original = job(attempt_count=1, requires_approval=True,
                       approval_received=True, risk_class=queue.APPROVAL_REQUIRED)
        before = asdict(original)
        updated, _ = self.adopt([original])
        self.assertEqual(asdict(original), before)
        expected = dict(before)
        expected.update(state=queue.RUNNING, attempt_count=2)
        self.assertEqual(asdict(updated), expected)

    def test_result_and_shared_validator(self):
        updated, result = self.adopt()
        self.assertEqual(result.reason_code, "JOB_EXECUTION_ADOPTION")
        self.assertEqual(result.occurred_at, UTC)
        self.assertEqual(queue.validate_job_transition_result(result).transition_class,
                         "EXECUTION_ADOPTION_TRANSITION")
        self.assertTrue(queue.validate_execution_adoption_transition(
            job(), updated, result, expected_job_id="job-a"))

    def test_occurred_at_must_be_explicit_aware_utc(self):
        for value in (None, "", "2026-08-31", "2026-08-31T01:02:03",
                      "2026-08-31T10:02:03+09:00", "not-a-time"):
            with self.subTest(value=value):
                self.assertIsNone(self.adopt(occurred_at=value)[0])
        self.assertEqual(self.adopt(occurred_at="2026-08-31T01:02:03+00:00")[0].state,
                         queue.RUNNING)

    def test_validator_rejects_plus_zero_plus_two_and_other_mutation(self):
        original = job()
        exact, result = self.adopt([original])
        self.assertTrue(queue.validate_execution_adoption_transition(
            original, exact, result, expected_job_id="job-a"))
        for candidate in (
            replace(original, state=queue.RUNNING),
            replace(original, state=queue.RUNNING, attempt_count=2),
            replace(exact, priority="P0"),
            replace(exact, job_id="other"),
            replace(exact, max_attempts=4),
            replace(exact, retry_policy="NONE"),
            replace(exact, approval_received=True, requires_approval=True),
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(queue.validate_execution_adoption_transition(
                    original, candidate, result, expected_job_id="job-a"))

    def test_validator_rejects_bad_result(self):
        original = job()
        candidate, result = self.adopt([original])
        for bad in (replace(result, reason_code="READY_JOB_SELECTED"),
                    replace(result, occurred_at="2026-08-31T10:02:03+09:00"),
                    replace(result, job_id="other")):
            self.assertFalse(queue.validate_execution_adoption_transition(
                original, candidate, bad, expected_job_id="job-a"))

    def test_completion_and_failed_safe_retain_generation(self):
        running, _ = self.adopt()
        self.assertEqual(queue.complete_job(running, expected_job_id="job-a")[0].attempt_count, 1)
        self.assertEqual(queue.fail_job_safe(running, expected_job_id="job-a")[0].attempt_count, 1)

    def test_checkpoint_copies_running_generation(self):
        running, _ = self.adopt()
        self.assertEqual(checkpoint(running).attempt_count, running.attempt_count)

    def test_resume_behavior_unchanged(self):
        value = job(state=queue.CHECKPOINTED, attempt_count=2)
        saved = checkpoint(value)
        decision = queue.resume_from_checkpoint(
            value, saved, now="2026-08-27T00:01:00+09:00",
            dependency_states={}, environment_preflight_passed=True)
        self.assertTrue(decision.resume_allowed)
        self.assertEqual(value.attempt_count, 2)


if __name__ == "__main__":
    unittest.main()
