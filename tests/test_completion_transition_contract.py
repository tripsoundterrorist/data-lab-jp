from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import unattended_job_queue as queue
from tests.test_unattended_job_queue import job, checkpoint


class CompletionContractTests(unittest.TestCase):
    def running(self):
        return job(state=queue.RUNNING)

    def complete(self, value=None):
        return queue.complete_job(self.running() if value is None else value, expected_job_id="job-a")

    def test_version(self):
        self.assertEqual(queue.COMPLETION_CONTRACT_VERSION, "0.1")

    def test_success(self):
        updated, result = self.complete()
        self.assertEqual(updated.state, queue.DONE)
        self.assertEqual(result.transition_status, "APPLIED")
        self.assertEqual((result.previous_state, result.new_state), (queue.RUNNING, queue.DONE))

    def test_identity(self):
        before = self.running()
        updated, result = self.complete(before)
        self.assertEqual((result.job_id, result.job_type), (before.job_id, before.job_type))
        self.assertEqual(updated.job_id, before.job_id)

    def test_shared_schema(self):
        _, approval = queue.apply_approval_with_transition(job(requires_approval=True), approval_event_received=False)
        _, completion = self.complete()
        self.assertIs(type(approval), type(completion))
        self.assertEqual(set(approval.to_dict()), set(completion.to_dict()))
        self.assertEqual(len(completion.to_dict()), 8)

    def test_fixed_utc(self):
        fixed = datetime(2026, 8, 27, 13, 4, 5, 123456, tzinfo=timezone.utc)
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            clock.now.return_value = fixed
            _, result = self.complete()
            for _ in range(5):
                self.assertEqual(json.loads(json.dumps(result.to_dict()))["occurred_at"], "2026-08-27T13:04:05.123456Z")
            clock.now.assert_called_once_with(timezone.utc)

    def test_repeated_completion(self):
        updated, first = self.complete()
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            second_job, second = self.complete(updated)
            clock.now.assert_not_called()
        self.assertIsNone(second_job)
        self.assertEqual(second.transition_status, "REJECTED")
        self.assertIsNone(second.occurred_at)
        self.assertEqual(updated.state, queue.DONE)
        self.assertIsNotNone(first.occurred_at)

    def test_missing_job(self):
        for value in (None, {}, "fixture-secret"):
            updated, result = queue.complete_job(value, expected_job_id="job-a")
            self.assertIsNone(updated)
            self.assertEqual(result.transition_status, "REJECTED")

    def test_invalid_identifier(self):
        for identifier in (None, "", "other-job", "fixture-secret", 1):
            updated, result = queue.complete_job(self.running(), expected_job_id=identifier)
            self.assertIsNone(updated)
            self.assertNotIn("fixture-secret", repr(result))

    def test_missing_identifier_argument(self):
        with self.assertRaises(TypeError):
            queue.complete_job(self.running())

    def test_invalid_job_data(self):
        for value in (replace(self.running(), job_id="fixture-secret"),
                      replace(self.running(), job_type=""),
                      replace(self.running(), created_at="bad"),
                      replace(self.running(), requires_approval=True, approval_received=False)):
            updated, result = self.complete(value)
            self.assertIsNone(updated)
            self.assertEqual(result.transition_status, "REJECTED")
            self.assertNotIn("fixture-secret", json.dumps(result.to_dict()))

    def test_preserves_all_other_fields(self):
        before = self.running()
        data = asdict(before)
        updated, _ = self.complete(before)
        self.assertEqual(asdict(before), data)
        data["state"] = queue.DONE
        self.assertEqual(asdict(updated), data)

    def test_frozen_results(self):
        updated, result = self.complete()
        with self.assertRaises(FrozenInstanceError):
            updated.state = queue.READY
        with self.assertRaises(FrozenInstanceError):
            result.occurred_at = "changed"

    def test_validator_accepts(self):
        before = self.running()
        updated, _ = self.complete(before)
        self.assertTrue(queue.validate_completion_transition(before, updated, expected_job_id="job-a"))

    def test_validator_rejects_modified_metadata(self):
        before = self.running()
        candidate = replace(before, state=queue.DONE, attempt_count=1)
        self.assertFalse(queue.validate_completion_transition(before, candidate, expected_job_id="job-a"))

    def test_validator_rejects_wrong_target(self):
        before = self.running()
        self.assertFalse(queue.validate_completion_transition(before, before, expected_job_id="job-a"))

    def test_clock_exception_no_partial_result(self):
        before = self.running()
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            clock.now.side_effect = RuntimeError("fixture-secret")
            updated, result = self.complete(before)
        self.assertIsNone(updated)
        self.assertEqual(before.state, queue.RUNNING)
        self.assertNotIn("fixture-secret", repr(result))

    def test_validation_failure_no_clock(self):
        with mock.patch.object(queue, "validate_completion_transition", return_value=False), mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            updated, result = self.complete()
            clock.now.assert_not_called()
        self.assertIsNone(updated)
        self.assertEqual(result.transition_status, "REJECTED")

    def test_replace_exception_no_partial_result(self):
        before = self.running()
        with mock.patch.object(queue, "replace", side_effect=RuntimeError("fixture-secret")):
            updated, result = self.complete(before)
        self.assertIsNone(updated)
        self.assertEqual(before.state, queue.RUNNING)
        self.assertEqual(result.transition_status, "REJECTED")

    def test_checkpoint_not_touched(self):
        before = self.running()
        cp = checkpoint(before)
        saved = cp.to_dict()
        self.complete(before)
        self.assertEqual(cp.to_dict(), saved)

    def test_approval_preserved(self):
        before = job(state=queue.RUNNING, requires_approval=True, approval_received=True)
        updated, _ = self.complete(before)
        self.assertTrue(updated.approval_received)
        self.assertTrue(updated.requires_approval)

    def test_selection_unchanged(self):
        updated, _ = self.complete()
        self.assertEqual(queue.select_next_job([updated]).status, "QUEUE_IDLE")
        self.assertEqual(queue.select_next_job([job("a", priority="P3"), job("b", priority="P0")]).selected_job_id, "b")

    def test_retry_unchanged(self):
        self.assertEqual(queue.assess_retry(job(), "POLICY_VIOLATION").state, queue.FAILED_SAFE)

    def test_queue_schema_unchanged(self):
        self.assertNotIn("queue_id", queue.select_next_job([]).to_dict())
        self.assertEqual(queue.select_next_job([job(state=queue.BLOCKED)]).status, "QUEUE_IDLE")
        self.assertEqual(len(asdict(job())), 16)

    def test_no_io_or_notification(self):
        with mock.patch("builtins.open", side_effect=AssertionError()), mock.patch.object(Path, "open", side_effect=AssertionError()), mock.patch.object(queue, "create_event", side_effect=AssertionError()) as event:
            self.assertEqual(self.complete()[1].transition_status, "APPLIED")
        event.assert_not_called()


def reject_state(state):
    def test(self):
        value = job(state=state)
        before = asdict(value)
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            updated, result = self.complete(value)
            clock.now.assert_not_called()
        self.assertIsNone(updated)
        self.assertEqual(result.transition_status, "REJECTED")
        self.assertIsNone(result.occurred_at)
        self.assertEqual(asdict(value), before)
    return test


for _state in (queue.READY, queue.WAITING_APPROVAL, queue.FAILED_SAFE, queue.BLOCKED,
               queue.DONE, queue.CANCELLED, queue.CHECKPOINTED, queue.RETRY_WAIT, "UNKNOWN"):
    setattr(CompletionContractTests, "test_reject_" + _state.lower(), reject_state(_state))


if __name__ == "__main__":
    unittest.main()
