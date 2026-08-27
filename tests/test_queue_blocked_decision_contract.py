from dataclasses import asdict, replace
from datetime import datetime
import ast
import json
from pathlib import Path
import unittest
from unittest import mock

from tests.test_unattended_job_queue import job, queue


def waiting(name="wait"):
    return job(name, state=queue.WAITING_APPROVAL, requires_approval=True)


class QueueBlockedDecisionTests(unittest.TestCase):
    def test_schema(self):
        d = queue.assess_queue_blocked([waiting()])
        self.assertEqual(set(d.to_dict()), {"decision_version", "decision_status", "blocked",
            "occurred_at", "blocker_class", "reason_code", "remaining_job_count"})
        self.assertEqual(d.decision_version, "0.1")

    def test_approval(self):
        d = queue.assess_queue_blocked([waiting()])
        self.assertTrue(d.blocked)
        self.assertEqual(d.blocker_class, "APPROVAL_BLOCKED")
        self.assertEqual(d.reason_code, "APPROVAL_REQUIRED_FOR_PROGRESS")

    def test_failed(self):
        d = queue.assess_queue_blocked([job(state=queue.FAILED_SAFE)])
        self.assertTrue(d.blocked)
        self.assertEqual(d.blocker_class, "FAILED_SAFE_BLOCKED")

    def test_mixed(self):
        d = queue.assess_queue_blocked([waiting(), job("failed", state=queue.FAILED_SAFE)])
        self.assertTrue(d.blocked)
        self.assertEqual(d.blocker_class, "MIXED_BLOCKED")

    def test_dependency_chain(self):
        jobs = [waiting(), job("b", dependencies=("wait",)), job("c", dependencies=("b",))]
        d = queue.assess_queue_blocked(jobs)
        self.assertTrue(d.blocked)
        self.assertEqual(d.remaining_job_count, 3)
        self.assertEqual(d.blocker_class, "APPROVAL_BLOCKED")
        self.assertEqual(d.to_dict() | {"occurred_at": None},
                         queue.assess_queue_blocked(list(reversed(jobs))).to_dict() | {"occurred_at": None})

    def test_failed_dependency(self):
        self.assertTrue(queue.assess_queue_blocked([
            job("f", state=queue.FAILED_SAFE), job(dependencies=("f",))]).blocked)

    def test_unknown_residual_prevents_proof(self):
        d = queue.assess_queue_blocked([waiting(), job("cp", state=queue.CHECKPOINTED),
                                       job("child", dependencies=("wait", "cp"))])
        self.assertFalse(d.blocked)
        self.assertEqual(d.decision_status, "UNKNOWN")

    def test_timestamp_once_and_serialization(self):
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            d = queue.assess_queue_blocked([waiting()])
            first = json.dumps(d.to_dict())
            self.assertEqual(first, json.dumps(d.to_dict()))
            clock.now.assert_called_once_with(queue.timezone.utc)
        self.assertEqual(datetime.fromisoformat(d.occurred_at.replace("Z", "+00:00")).utcoffset().total_seconds(), 0)

    def test_no_idle_timestamp(self):
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            for jobs in ([], [job(state=queue.DONE)], [job()], [job(state=queue.CHECKPOINTED)]):
                self.assertIsNone(queue.assess_queue_blocked(jobs).occurred_at)
            clock.now.assert_not_called()

    def test_existing_selection_unchanged(self):
        jobs = [waiting()]
        before = queue.select_next_job(jobs)
        self.assertEqual(before.status, "QUEUE_IDLE")
        self.assertTrue(queue.assess_queue_blocked(jobs).blocked)
        self.assertEqual(before, queue.select_next_job(jobs))

    def test_existing_invalid_blocked_is_not_proof(self):
        jobs = [job(dependencies=("missing",))]
        self.assertEqual(queue.select_next_job(jobs).status, "QUEUE_BLOCKED")
        self.assertFalse(queue.assess_queue_blocked(jobs).blocked)

    def test_read_only(self):
        jobs = [waiting(), job("child", dependencies=("wait",))]
        before = [asdict(j) for j in jobs]
        with mock.patch.object(queue, "apply_approval", side_effect=AssertionError()), \
             mock.patch.object(queue, "assess_retry", side_effect=AssertionError()), \
             mock.patch.object(queue, "resume_from_checkpoint", side_effect=AssertionError()), \
             mock.patch.object(queue, "switch_after_pause", side_effect=AssertionError()), \
             mock.patch.object(queue, "create_event", side_effect=AssertionError()):
            self.assertTrue(queue.assess_queue_blocked(jobs).blocked)
        self.assertEqual(before, [asdict(j) for j in jobs])

    def test_no_io_or_notification_dependencies(self):
        tree = ast.parse(Path(queue.__file__).read_text(encoding="utf-8"))
        imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual({n.module if isinstance(n, ast.ImportFrom) else n.names[0].name for n in imports},
                         {"__future__", "dataclasses", "datetime", "re", "typing"})
        self.assertNotIn("queue_id", queue.QueueBlockedDecision.__dataclass_fields__)

    def test_direct_construction_not_authenticated(self):
        d = queue.assess_queue_blocked([waiting()])
        self.assertTrue(queue.validate_queue_blocked_decision(queue.QueueBlockedDecision(**d.to_dict())))

    def test_nonblocked_validator_false(self):
        self.assertFalse(queue.validate_queue_blocked_decision(queue.assess_queue_blocked([])))

    def test_malformed_objects(self):
        for d in (None, {}, [], "secret", queue.select_next_job([])):
            self.assertFalse(queue.validate_queue_blocked_decision(d))

    def test_no_raw_error(self):
        with mock.patch.object(queue, "validate_queue", side_effect=ValueError("sensitive-value")):
            d = queue.assess_queue_blocked([waiting()])
        self.assertFalse(d.blocked)
        self.assertNotIn("sensitive-value", repr(d))

    def test_existing_cycle_detection(self):
        jobs = [job("a", dependencies=("b",)), job("b", dependencies=("a",))]
        with mock.patch.object(queue, "_cycle", wraps=queue._cycle) as cycle:
            self.assertFalse(queue.assess_queue_blocked(jobs).blocked)
            cycle.assert_called()


def case(jobs, status, **options):
    def test(self):
        d = queue.assess_queue_blocked(jobs, **options)
        self.assertFalse(d.blocked)
        self.assertIsNone(d.occurred_at)
        self.assertEqual(d.decision_status, status)
    return test


for name, jobs, status, options in [
    ("empty", [], "QUEUE_IDLE", {}),
    ("done", [job(state=queue.DONE)], "QUEUE_IDLE", {}),
    ("ready", [job()], "NOT_BLOCKED", {}),
    ("running", [job(state=queue.RUNNING)], "NOT_BLOCKED", {}),
    ("waiting_ready", [waiting(), job()], "NOT_BLOCKED", {}),
    ("failed_ready", [job("f", state=queue.FAILED_SAFE), job()], "NOT_BLOCKED", {}),
    ("waiting_running", [waiting(), job(state=queue.RUNNING)], "NOT_BLOCKED", {}),
    ("checkpoint", [job(state=queue.CHECKPOINTED)], "UNKNOWN", {}),
    ("retry", [job(state=queue.RETRY_WAIT)], "UNKNOWN", {}),
    ("cancelled", [job(state=queue.CANCELLED)], "UNKNOWN", {}),
    ("blocked_state", [job(state=queue.BLOCKED)], "UNKNOWN", {}),
    ("blocker_code", [job(blocker_codes=("POLICY_BLOCK",))], "UNKNOWN", {}),
    ("missing_dep", [job(dependencies=("absent",))], "UNKNOWN", {}),
    ("bad_state", [job(state="UNKNOWN")], "UNKNOWN", {}),
    ("bad_queue", None, "UNKNOWN", {}),
    ("duplicate", [job(), job()], "UNKNOWN", {}),
    ("waiting_no_approval_flag", [job(state=queue.WAITING_APPROVAL)], "UNKNOWN", {}),
    ("waiting_already_approved", [replace(waiting(), approval_received=True)], "UNKNOWN", {}),
    ("ready_unapproved", [job(requires_approval=True)], "UNKNOWN", {}),
    ("window_unknown", [job(deadline_class="HARD")], "UNKNOWN", {}),
    ("window_closed", [job(deadline_class="HARD")], "UNKNOWN", {"window_states": {"job-a": "CLOSED"}}),
    ("window_open", [job(deadline_class="HARD")], "NOT_BLOCKED", {"window_states": {"job-a": "OPEN"}}),
    ("external_allowed", [job(risk_class=queue.EXTERNAL_READ)], "NOT_BLOCKED", {"external_read_allowed": True}),
    ("external_denied", [job(risk_class=queue.EXTERNAL_READ)], "UNKNOWN", {}),
    ("bad_context", [waiting()], "UNKNOWN", {"external_read_allowed": 1}),
    ("bad_window", [waiting()], "UNKNOWN", {"window_states": {"wait": "INVALID"}}),
]:
    setattr(QueueBlockedDecisionTests, "test_case_" + name, case(jobs, status, **options))


def invalid(change):
    def test(self):
        d = replace(queue.assess_queue_blocked([waiting()]), **change)
        self.assertFalse(queue.validate_queue_blocked_decision(d))
    return test


for name, change in {
    "version": {"decision_version": "9"}, "status": {"decision_status": "QUEUE_IDLE"},
    "bool": {"blocked": 1}, "false": {"blocked": False}, "count": {"remaining_job_count": 0},
    "bool_count": {"remaining_job_count": True}, "class": {"blocker_class": "UNKNOWN"},
    "reason": {"reason_code": "FREE_FORM"}, "time": {"occurred_at": "bad"},
    "naive": {"occurred_at": "2026-08-27T00:00:00"},
    "offset": {"occurred_at": "2026-08-27T00:00:00+09:00"},
    "mixed_count": {"blocker_class": "MIXED_BLOCKED", "reason_code": "MULTIPLE_PROVEN_BLOCKERS"},
}.items():
    setattr(QueueBlockedDecisionTests, "test_invalid_" + name, invalid(change))


if __name__ == "__main__":
    unittest.main()
