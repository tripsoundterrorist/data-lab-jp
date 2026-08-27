import ast
from dataclasses import asdict, replace
from datetime import datetime
import inspect
import json
import unittest
from unittest import mock

from tests.test_unattended_job_queue import job, queue
import pushover_notification_adapter as adapter
import unattended_runtime as runtime


class QueueBlockedFactoryTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [job("wait", state=queue.WAITING_APPROVAL, requires_approval=True)]
        self.decision = queue.assess_queue_blocked(self.jobs)
        self.identity = queue.get_queue_identity()

    def build(self):
        return queue.build_queue_blocked_safe_event(self.decision, self.identity)

    def test_version(self):
        self.assertEqual(queue.QUEUE_BLOCKED_FACTORY_VERSION, "0.1")

    def test_metadata_schema(self):
        event = self.build()
        self.assertIsInstance(event, queue.QueueNotificationEventV02)
        self.assertEqual(event.to_dict(), {
            "event_version": "0.2", "subject_type": "QUEUE", "event_type": "QUEUE_BLOCKED",
            "severity": "ERROR", "state": "QUEUE_BLOCKED", "summary_code": "QUEUE_BLOCKED",
            "approval_required": False, "queue_id": self.identity.queue_id,
            "occurred_at": self.decision.occurred_at,
        })
        self.assertEqual(set(event.to_dict()), queue.V02_QUEUE_FIELDS)
        self.assertNotIn("job_id", event.to_dict())
        self.assertNotIn("job_type", event.to_dict())

    def test_schema_validator(self):
        event = self.build()
        self.assertEqual(queue.create_event(**event.to_dict()), event)

    def test_validator_order(self):
        calls = []
        decision_validator = queue.validate_queue_blocked_decision
        identity_validator = queue.validate_queue_identity
        def validate_decision(d):
            calls.append("decision")
            return decision_validator(d)
        def validate_identity(i):
            calls.append("identity")
            return identity_validator(i)
        with mock.patch.object(queue, "validate_queue_blocked_decision", side_effect=validate_decision), \
             mock.patch.object(queue, "validate_queue_identity", side_effect=validate_identity):
            self.assertIsNotNone(self.build())
        self.assertEqual(calls[:2], ["decision", "identity"])

    def test_decision_validation_failure(self):
        for result in (False, None, 1):
            with mock.patch.object(queue, "validate_queue_blocked_decision", return_value=result), \
                 mock.patch.object(queue, "create_event") as create:
                self.assertIsNone(self.build())
                create.assert_not_called()

    def test_identity_validation_failure(self):
        for result in (False, None, 1):
            with mock.patch.object(queue, "validate_queue_identity", return_value=result), \
                 mock.patch.object(queue, "create_event") as create:
                self.assertIsNone(self.build())
                create.assert_not_called()

    def test_exceptions_fail_closed(self):
        for name in ("validate_queue_blocked_decision", "validate_queue_identity", "create_event"):
            with mock.patch.object(queue, name, side_effect=ValueError("fixture-private")):
                self.assertIsNone(self.build())

    def test_schema_failure(self):
        with mock.patch.object(queue, "create_event", return_value=None):
            self.assertIsNone(self.build())

    def test_timestamp_exact_no_clock(self):
        self.decision = replace(self.decision, occurred_at="2026-08-27T00:00:00.123456+00:00")
        with mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            event = self.build()
            self.assertEqual(event.occurred_at, self.decision.occurred_at)
            clock.now.assert_not_called()

    def test_deterministic(self):
        self.assertEqual(json.dumps(self.build().to_dict()), json.dumps(self.build().to_dict()))

    def test_no_own_hash_or_metadata_analysis(self):
        tree = ast.parse(inspect.getsource(queue.build_queue_blocked_safe_event))
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertEqual(calls, {"validate_queue_blocked_decision", "validate_queue_identity", "create_event"})
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(attrs, {"queue_id", "occurred_at"})
        self.assertNotIn(self.identity.queue_id, inspect.getsource(queue.build_queue_blocked_safe_event))

    def test_runtime_identity_is_external(self):
        first, second = self.build(), self.build()
        self.assertEqual(runtime.event_identity(first), runtime.event_identity(second))

    def test_adapter_policy(self):
        output = adapter.adapt_notification(self.build())
        self.assertEqual(output.notification_status, "READY")
        self.assertEqual((output.pushover_priority, output.delivery_class), (1, "IMMEDIATE"))
        self.assertEqual((output.title, output.message), adapter.MAPPINGS["QUEUE_BLOCKED"][2:])

    def test_no_mutation_or_recovery(self):
        before = ([asdict(j) for j in self.jobs], self.decision.to_dict(), self.identity.to_dict())
        with mock.patch.object(queue, "assess_queue_blocked", side_effect=AssertionError()), \
             mock.patch.object(queue, "apply_approval", side_effect=AssertionError()), \
             mock.patch.object(queue, "assess_retry", side_effect=AssertionError()), \
             mock.patch.object(queue, "resume_from_checkpoint", side_effect=AssertionError()), \
             mock.patch.object(queue, "select_next_job", side_effect=AssertionError()), \
             mock.patch.object(runtime, "process_notification", side_effect=AssertionError()), \
             mock.patch.object(adapter, "adapt_notification", side_effect=AssertionError()):
            self.assertIsNotNone(self.build())
        self.assertEqual(before, ([asdict(j) for j in self.jobs], self.decision.to_dict(), self.identity.to_dict()))

    def test_direct_construction_not_origin_proof(self):
        self.decision = queue.QueueBlockedDecision(**self.decision.to_dict())
        self.identity = queue.QueueIdentity(**self.identity.to_dict())
        self.assertIsNotNone(self.build())

    def test_no_payload_from_decision(self):
        event = self.build().to_dict()
        for field in ("blocker_class", "reason_code", "remaining_job_count", "priority", "message", "delivery_class"):
            self.assertNotIn(field, event)


def roots_case(kind):
    def test(self):
        jobs = {
            "approval": self.jobs,
            "failed": [job(state=queue.FAILED_SAFE)],
            "mixed": self.jobs + [job("failed", state=queue.FAILED_SAFE)],
        }[kind]
        self.decision = queue.assess_queue_blocked(jobs)
        self.assertTrue(self.decision.blocked)
        self.assertEqual(self.build().severity, "ERROR")
    return test


for _kind in ("approval", "failed", "mixed"):
    setattr(QueueBlockedFactoryTests, "test_severity_" + _kind, roots_case(_kind))


def reject_case(target, changes):
    def test(self):
        setattr(self, target, replace(getattr(self, target), **changes))
        self.assertIsNone(self.build())
    return test


for _name, _target, _changes in [
    ("decision_version", "decision", {"decision_version": "9"}),
    ("unknown", "decision", {"decision_status": "UNKNOWN", "blocked": False}),
    ("not_blocked", "decision", {"decision_status": "NOT_BLOCKED", "blocked": False}),
    ("idle", "decision", {"decision_status": "QUEUE_IDLE", "blocked": False}),
    ("false", "decision", {"blocked": False}),
    ("timestamp", "decision", {"occurred_at": "bad"}),
    ("reason", "decision", {"reason_code": "UNSUPPORTED"}),
    ("class", "decision", {"blocker_class": "UNSUPPORTED"}),
    ("count", "decision", {"remaining_job_count": 0}),
    ("identity_version", "identity", {"identity_version": "9"}),
    ("queue_id", "identity", {"queue_id": "other"}),
    ("identity_status", "identity", {"identity_status": "UNKNOWN"}),
]:
    setattr(QueueBlockedFactoryTests, "test_reject_" + _name, reject_case(_target, _changes))


def malformed_case(target):
    def test(self):
        for value in (None, {}, [], "fixture-private"):
            setattr(self, target, value)
            self.assertIsNone(self.build())
    return test


for _target in ("decision", "identity"):
    setattr(QueueBlockedFactoryTests, "test_malformed_" + _target, malformed_case(_target))


if __name__ == "__main__":
    unittest.main()
