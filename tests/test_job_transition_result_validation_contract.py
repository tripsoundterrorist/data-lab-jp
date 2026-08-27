from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import unattended_job_queue as queue
from tests.test_unattended_job_queue import job, checkpoint


class ResultValidationTests(unittest.TestCase):
    def setUp(self):
        self.running = job(state=queue.RUNNING)
        self.failed = queue.fail_job_safe(self.running, expected_job_id="job-a")[1]
        self.done = queue.complete_job(self.running, expected_job_id="job-a")[1]
        self.waiting = queue.apply_approval_with_transition(job(requires_approval=True), approval_event_received=False)[1]

    def validate(self, result):
        return queue.validate_job_transition_result(result)

    def test_version_and_schema(self):
        result = self.validate(self.done)
        self.assertEqual(result.validation_version, "0.1")
        self.assertEqual(set(result.to_dict()), {"validation_version", "valid", "transition_class", "reason_code"})

    def test_official_three_classes(self):
        for source, expected in ((self.waiting, "APPROVAL_WAITING_TRANSITION"),
                                 (self.failed, "FAILED_SAFE_TRANSITION"), (self.done, "COMPLETION_TRANSITION")):
            result = self.validate(source)
            self.assertTrue(result.valid)
            self.assertEqual(result.transition_class, expected)

    def test_approval_ready(self):
        source = queue.apply_approval_with_transition(job(state=queue.WAITING_APPROVAL, requires_approval=True),
                                                       approval_event_received=True)[1]
        self.assertEqual(self.validate(source).transition_class, "APPROVAL_READY_TRANSITION")

    def test_all_existing_approval_pairs(self):
        # Real Core outputs, not an independently constructed transition matrix.
        for state in queue.JOB_STATES:
            for signal in (False, True):
                value = job(state=state, requires_approval=True, approval_received=(state == queue.RUNNING))
                updated, source = queue.apply_approval_with_transition(value, approval_event_received=signal)
                self.assertIsNotNone(updated)
                result = self.validate(source)
                self.assertEqual(result.valid, source.transition_status == "APPLIED")

    def test_utc_forms(self):
        for stamp in ("2026-08-27T00:00:00Z", "2026-08-27T00:00:00+00:00", "2026-08-27T00:00:00.123456Z"):
            source = replace(self.done, occurred_at=stamp)
            self.assertTrue(self.validate(source).valid)
            self.assertEqual(source.occurred_at, stamp)

    def test_no_clock_generation(self):
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            for _ in range(5):
                self.assertTrue(self.validate(self.done).valid)
            clock.now.assert_not_called()

    def test_immutable_output(self):
        result = self.validate(self.done)
        with self.assertRaises(FrozenInstanceError):
            result.valid = False
        view = result.to_dict()
        view["valid"] = False
        self.assertTrue(result.valid)

    def test_no_origin_authentication(self):
        direct = queue.JobTransitionResult(**self.done.to_dict())
        self.assertIsNot(direct, self.done)
        self.assertTrue(self.validate(direct).valid)

    def test_no_replay_or_freshness_proof(self):
        historical = replace(self.done, occurred_at="2000-01-01T00:00:00Z")
        self.assertEqual(self.validate(historical), self.validate(historical))
        self.assertTrue(self.validate(historical).valid)

    def test_rejected_and_unchanged(self):
        rejected = queue.complete_job(job(), expected_job_id="job-a")[1]
        unchanged = queue.apply_approval_with_transition(job(state=queue.WAITING_APPROVAL), approval_event_received=False)[1]
        for result in (rejected, unchanged):
            self.assertFalse(self.validate(result).valid)

    def test_wrong_types(self):
        for value in (None, {}, self.done.to_dict(), "fixture-secret", self.running):
            self.assertFalse(self.validate(value).valid)

    def test_subclass_rejected(self):
        class Derived(queue.JobTransitionResult):
            pass
        self.assertFalse(self.validate(Derived(**self.done.to_dict())).valid)

    def test_extra_field(self):
        source = queue.JobTransitionResult(**self.done.to_dict())
        object.__setattr__(source, "extra", "fixture-secret")
        self.assertFalse(self.validate(source).valid)

    def test_missing_field(self):
        source = queue.JobTransitionResult(**self.done.to_dict())
        object.__delattr__(source, "job_id")
        self.assertFalse(self.validate(source).valid)

    def test_unsafe_output(self):
        for field in self.done.to_dict():
            result = self.validate(replace(self.done, **{field: "fixture-secret"}))
            self.assertFalse(result.valid)
            self.assertNotIn("fixture-secret", json.dumps(result.to_dict()))

    def test_read_only_no_operations(self):
        before = self.done.to_dict()
        cp = checkpoint()
        cp_before = cp.to_dict()
        original = asdict(self.running)
        with mock.patch.object(queue, "apply_approval", side_effect=AssertionError()), mock.patch.object(
                queue, "complete_job", side_effect=AssertionError()), mock.patch.object(
                queue, "fail_job_safe", side_effect=AssertionError()), mock.patch.object(
                queue, "assess_retry", side_effect=AssertionError()), mock.patch.object(
                queue, "select_next_job", side_effect=AssertionError()), mock.patch.object(
                queue, "create_event", side_effect=AssertionError()), mock.patch.object(
                Path, "open", side_effect=AssertionError()):
            self.assertTrue(self.validate(self.done).valid)
        self.assertEqual(before, self.done.to_dict())
        self.assertEqual(original, asdict(self.running))
        self.assertEqual(cp_before, cp.to_dict())

    def test_queue_decision_not_transition(self):
        decision = queue.select_next_job([])
        self.assertEqual(decision.status, "QUEUE_IDLE")
        self.assertNotIn("queue_id", decision.to_dict())
        self.assertFalse(self.validate(decision).valid)


INVALID_CASES = {
    "version": {"transition_version": "9"},
    "missing_id": {"job_id": None}, "empty_id": {"job_id": ""},
    "unsafe_id": {"job_id": "C:/private"}, "invalid_type": {"job_type": "http://private"},
    "previous_unknown": {"previous_state": "UNKNOWN"}, "new_unknown": {"new_state": "UNKNOWN"},
    "ready_done": {"previous_state": queue.READY}, "failed_done": {"previous_state": queue.FAILED_SAFE},
    "done_done": {"previous_state": queue.DONE},
    "ready_failed": {"previous_state": queue.READY, "new_state": queue.FAILED_SAFE, "reason_code": "FAILED_SAFE_CONFIRMED"},
    "done_failed": {"previous_state": queue.DONE, "new_state": queue.FAILED_SAFE, "reason_code": "FAILED_SAFE_CONFIRMED"},
    "failed_wrong_reason": {"new_state": queue.FAILED_SAFE},
    "done_wrong_reason": {"reason_code": "FAILED_SAFE_CONFIRMED"},
    "approval_wrong_reason": {"new_state": queue.WAITING_APPROVAL},
    "approval_wrong_target": {"reason_code": "APPROVAL_STATE_TRANSITION"},
    "applied_rejection_reason": {"reason_code": "COMPLETION_TRANSITION_INVALID"},
    "rejected": {"transition_status": "REJECTED"},
    "unknown_status": {"transition_status": "UNKNOWN"},
    "invalid_time": {"occurred_at": "not-a-time"}, "naive": {"occurred_at": "2026-08-27T00:00:00"},
    "date_only": {"occurred_at": "2026-08-27"}, "non_utc": {"occurred_at": "2026-08-27T09:00:00+09:00"},
    "invalid_date": {"occurred_at": "2026-02-30T00:00:00Z"},
    "unhashable": {"previous_state": []}, "boolean_version": {"transition_version": True},
    "queue_blocked": {"new_state": "QUEUE_BLOCKED"}, "queue_idle": {"new_state": "QUEUE_IDLE"},
}


def invalid_case(changes):
    def test(self):
        result = self.validate(replace(self.done, **changes))
        self.assertFalse(result.valid)
        self.assertEqual(result.transition_class, "UNSUPPORTED")
        self.assertEqual(result.reason_code, "TRANSITION_RESULT_INVALID")
    return test


for _name, _changes in INVALID_CASES.items():
    setattr(ResultValidationTests, "test_invalid_" + _name, invalid_case(_changes))


if __name__ == "__main__":
    unittest.main()
