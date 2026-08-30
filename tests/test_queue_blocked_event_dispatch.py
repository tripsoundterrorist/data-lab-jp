import ast
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_unattended_job_queue import job, queue
from tests.test_unattended_runtime import event as job_event
import queue_blocked_event_dispatch as dispatch
import unattended_runtime as runtime
import pushover_notification_adapter as adapter
import pushover_sender as sender
import notification_ledger as ledger
import ledger_recovery as recovery


class QueueBlockedDispatchTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [job("wait", state=queue.WAITING_APPROVAL, requires_approval=True)]
        self.decision = queue.assess_queue_blocked(self.jobs)
        self.identity = queue.get_queue_identity()
        self.temp = tempfile.TemporaryDirectory(prefix="blocked-dispatch-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.path.write_text("[]\n", encoding="utf-8")
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-private-response"})
        for name in ("_default_transport", "load_credentials"):
            patcher = mock.patch.object(sender, name, side_effect=AssertionError("REAL_IO_FORBIDDEN"))
            self.addCleanup(patcher.stop)
            patched = patcher.start()
            self.addCleanup(patched.assert_not_called)

    def execute(self, **kwargs):
        options = dict(mode="MOCK_RUNTIME", ledger=self.store,
                       credential_loader=self.loader, transport=self.transport)
        options.update(kwargs)
        return dispatch.dispatch_queue_blocked(self.decision, self.identity, **options)

    def test_version_result(self):
        r = self.execute()
        self.assertEqual(r.dispatch_version, "0.1")
        self.assertEqual(len(r.to_dict()), 7)
        self.assertEqual(r.dispatch_status, "COMPLETED")

    def test_factory_exact_object_handoff(self):
        source = queue.build_queue_blocked_safe_event(self.decision, self.identity)
        with mock.patch.object(queue, "build_queue_blocked_safe_event", return_value=source) as factory, \
             mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as run:
            r = self.execute(mode="DRY_RUN")
        factory.assert_called_once_with(self.decision, self.identity)
        run.assert_called_once()
        self.assertIs(run.call_args.args[0], source)
        self.assertTrue(r.event_generated)
        self.assertTrue(r.runtime_handoff)

    def test_factory_none(self):
        with mock.patch.object(queue, "build_queue_blocked_safe_event", return_value=None), \
             mock.patch.object(runtime, "process_notification") as run:
            r = self.execute()
        run.assert_not_called()
        self.assertFalse(r.event_generated)
        self.assertEqual(r.dispatch_status, "BLOCKED")

    def test_factory_exception(self):
        with mock.patch.object(queue, "build_queue_blocked_safe_event", side_effect=ValueError("fixture-secret")), \
             mock.patch.object(runtime, "process_notification") as run:
            r = self.execute()
        run.assert_not_called()
        self.assertFalse(r.event_generated)
        self.assertNotIn("fixture-secret", repr(r))

    def test_factory_malformed_output(self):
        for value in ({}, True, "fixture-secret"):
            with mock.patch.object(queue, "build_queue_blocked_safe_event", return_value=value), \
                 mock.patch.object(runtime, "process_notification") as run:
                self.assertFalse(self.execute().event_generated)
            run.assert_not_called()

    def test_no_metadata_or_source_validation(self):
        tree = ast.parse(Path(dispatch.__file__).read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(n, ast.Dict) for n in ast.walk(tree)))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for field in ("queue_id", "occurred_at", "severity", "state", "summary_code", "blocked",
                      "blocker_class", "remaining_job_count", "now", "sha256", "assess_queue_blocked",
                      "validate_queue_identity", "validate_queue_blocked_decision"):
            self.assertNotIn(field, attrs)
        constants = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for value in ("QUEUE_BLOCKED", "QUEUE", "ERROR", queue.MAIN_QUEUE_ID):
            self.assertNotIn(value, constants)
        self.assertEqual({n.names[0].name for n in tree.body if isinstance(n, ast.Import)},
                         {"unattended_job_queue", "unattended_runtime"})

    def test_schema_timestamp(self):
        self.decision = replace(self.decision, occurred_at="2026-08-27T00:00:00.123456+00:00")
        with mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as run, \
             mock.patch.object(queue, "datetime", wraps=datetime) as clock:
            self.execute(mode="DRY_RUN")
            source = run.call_args.args[0]
            clock.now.assert_not_called()
        self.assertEqual(source, queue.build_queue_blocked_safe_event(self.decision, self.identity))
        self.assertEqual(source.occurred_at, self.decision.occurred_at)
        self.assertEqual(source.queue_id, self.identity.queue_id)
        self.assertEqual(set(source.to_dict()), queue.V02_QUEUE_FIELDS)
        self.assertEqual((source.event_version, source.subject_type, source.event_type), ("0.2", "QUEUE", "QUEUE_BLOCKED"))
        self.assertEqual((source.state, source.severity, source.approval_required, source.summary_code),
                         ("QUEUE_BLOCKED", "ERROR", False, "QUEUE_BLOCKED"))

    def test_identity(self):
        with mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as run:
            self.execute(mode="DRY_RUN")
            first = run.call_args.args[0]
            self.execute(mode="DRY_RUN")
            second = run.call_args.args[0]
            self.decision = replace(self.decision, occurred_at="2030-01-01T00:00:00Z")
            self.execute(mode="DRY_RUN")
            third = run.call_args.args[0]
        self.assertEqual(first, second)
        self.assertEqual(runtime.event_identity(first), runtime.event_identity(second))
        self.assertNotEqual(runtime.event_identity(first), runtime.event_identity(third))
        for kind in ("JOB_WAITING_APPROVAL", "JOB_FAILED_SAFE", "JOB_COMPLETED"):
            self.assertNotEqual(runtime.event_identity(first), runtime.event_identity(job_event(kind)))

    def test_dry_run(self):
        before = self.path.read_bytes()
        r = self.execute(mode="DRY_RUN")
        self.assertEqual(r.runtime_status, "NOTIFICATION_READY")
        self.transport.assert_not_called()
        self.assertEqual(before, self.path.read_bytes())

    @unittest.skipUnless(ledger.DEFAULT_PATH.is_file(),
                         "production notification ledger is not present")
    def test_default_dry_production_read_only(self):
        before = ledger.DEFAULT_PATH.read_bytes()
        r = dispatch.dispatch_queue_blocked(self.decision, self.identity, credential_loader=self.loader)
        self.assertEqual(r.runtime_mode, "DRY_RUN")
        self.assertEqual(r.runtime_status, "NOTIFICATION_READY")
        self.assertEqual(before, ledger.DEFAULT_PATH.read_bytes())

    def test_mock_delivery_and_adapter(self):
        with mock.patch.object(adapter, "_adapt", wraps=adapter._adapt) as adapt, \
             mock.patch.object(runtime, "inspect_ledger", wraps=runtime.inspect_ledger) as inspect:
            r = self.execute()
        self.assertEqual(r.runtime_status, "NOTIFICATION_DELIVERED")
        adapt.assert_called_once()
        inspect.assert_called_once()
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 1)
        self.transport.assert_called_once()
        actual = adapter.adapt_notification(adapt.call_args.args[0])
        self.assertEqual((actual.pushover_priority, actual.delivery_class), (1, "IMMEDIATE"))
        self.assertEqual(actual.message, adapter.MAPPINGS["QUEUE_BLOCKED"][3])

    def test_duplicate_sender_not_reached(self):
        self.execute()
        before = self.path.read_bytes()
        self.transport.reset_mock()
        self.loader.reset_mock()
        with mock.patch.object(sender, "_send", side_effect=AssertionError()) as send:
            r = self.execute()
        self.assertEqual(r.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
        send.assert_not_called()
        self.transport.assert_not_called()
        self.loader.assert_not_called()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 1)

    def test_failure_isolation(self):
        before = ([asdict(j) for j in self.jobs], self.decision.to_dict(), self.identity.to_dict())
        for target, name, error in ((runtime, "process_notification", ValueError("fixture-private")),
                                    (sender, "_send", ValueError("fixture-private")),
                                    (ledger.NotificationLedger, "_replace", ledger.LedgerError("LEDGER_WRITE_FAILED"))):
            with mock.patch.object(target, name, side_effect=error):
                r = self.execute()
            self.assertEqual(r.dispatch_status, "FAILED_SAFE")
            self.assertEqual(before, ([asdict(j) for j in self.jobs], self.decision.to_dict(), self.identity.to_dict()))
            self.assertNotIn("fixture-private", repr(r))

    def test_no_recovery_mutation(self):
        with mock.patch.object(queue, "apply_approval", side_effect=AssertionError()), \
             mock.patch.object(queue, "assess_retry", side_effect=AssertionError()), \
             mock.patch.object(queue, "resume_from_checkpoint", side_effect=AssertionError()), \
             mock.patch.object(queue, "switch_after_pause", side_effect=AssertionError()):
            self.assertEqual(self.execute().dispatch_status, "COMPLETED")

    def test_runtime_invalid_response(self):
        for value in (None, {}, "fixture-secret"):
            with mock.patch.object(runtime, "process_notification", return_value=value):
                r = self.execute()
            self.assertEqual(r.reason_code, "RUNTIME_RESULT_INVALID")
            self.assertNotIn("fixture-secret", repr(r))

    def test_runtime_unknown_status(self):
        good = runtime.process_notification(queue.build_queue_blocked_safe_event(self.decision, self.identity),
                                            ledger=self.store, credential_loader=self.loader)
        with mock.patch.object(runtime, "process_notification", return_value=replace(good, runtime_status="fixture-secret")):
            r = self.execute(mode="DRY_RUN")
        self.assertEqual(r.reason_code, "RUNTIME_RESULT_INVALID")
        self.assertNotIn("fixture-secret", repr(r))

    def test_mock_requires_fixtures(self):
        with mock.patch.object(runtime, "process_notification") as run:
            r = dispatch.dispatch_queue_blocked(self.decision, self.identity, mode="MOCK_RUNTIME")
        run.assert_not_called()
        self.assertFalse(r.event_generated)

    def test_unknown_mode(self):
        for mode in (None, [], "UNSUPPORTED"):
            with mock.patch.object(runtime, "process_notification") as run:
                self.assertEqual(self.execute(mode=mode).dispatch_status, "BLOCKED")
            run.assert_not_called()

    def test_safe_output(self):
        output = json.dumps(self.execute().to_dict())
        for value in ("fixture-user", "fixture-app", "fixture-private-response", "payload", "traceback",
                      adapter.MAPPINGS["QUEUE_BLOCKED"][3], self.identity.queue_id, self.decision.occurred_at):
            self.assertNotIn(value, output)

    def test_direct_construction_limit(self):
        self.decision = queue.QueueBlockedDecision(**self.decision.to_dict())
        self.identity = queue.QueueIdentity(**self.identity.to_dict())
        self.assertEqual(self.execute().dispatch_status, "COMPLETED")

    def test_existing_emergency_block(self):
        r = runtime.process_notification(job_event("CRITICAL_STOP"), mode="MOCK_RUNTIME", ledger=self.store,
                                         credential_loader=self.loader, transport=self.transport)
        self.assertEqual(r.runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.transport.assert_not_called()


def invalid_case(target, change):
    def test(self):
        setattr(self, target, replace(getattr(self, target), **change))
        with mock.patch.object(runtime, "process_notification") as run:
            r = self.execute()
        run.assert_not_called()
        self.assertFalse(r.event_generated)
        self.assertFalse(r.runtime_handoff)
    return test


for _name, _target, _change in [
    ("idle", "decision", {"decision_status": "QUEUE_IDLE", "blocked": False}),
    ("unknown", "decision", {"decision_status": "UNKNOWN", "blocked": False}),
    ("not_blocked", "decision", {"decision_status": "NOT_BLOCKED", "blocked": False}),
    ("false", "decision", {"blocked": False}),
    ("version", "decision", {"decision_version": "9"}),
    ("time", "decision", {"occurred_at": "bad"}),
    ("reason", "decision", {"reason_code": "UNKNOWN"}),
    ("class", "decision", {"blocker_class": "UNKNOWN"}),
    ("identity", "identity", {"queue_id": "unknown"}),
    ("identity_version", "identity", {"identity_version": "9"}),
]:
    setattr(QueueBlockedDispatchTests, "test_invalid_" + _name, invalid_case(_target, _change))


def malformed(target):
    def test(self):
        for value in (None, {}, [], "fixture-secret"):
            setattr(self, target, value)
            with mock.patch.object(runtime, "process_notification") as run:
                self.assertFalse(self.execute().event_generated)
            run.assert_not_called()
    return test


for _target in ("decision", "identity"):
    setattr(QueueBlockedDispatchTests, "test_malformed_" + _target, malformed(_target))


if __name__ == "__main__":
    unittest.main()
