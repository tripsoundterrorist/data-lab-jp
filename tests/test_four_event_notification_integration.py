from dataclasses import asdict
from itertools import combinations
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_unattended_job_queue import job, checkpoint, queue
from tests.test_unattended_runtime import event as existing_event
import job_level_event_dispatch as job_dispatch
import queue_blocked_event_dispatch as queue_dispatch
import unattended_runtime as runtime
import pushover_notification_adapter as adapter
import pushover_sender as sender
import notification_ledger as ledger
import ledger_recovery as recovery


INTEGRATED_VERSION = "0.1"
KINDS = ("JOB_WAITING_APPROVAL", "JOB_FAILED_SAFE", "JOB_COMPLETED", "QUEUE_BLOCKED")


class FourEventIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [job("waiting", requires_approval=True), job("running", state=queue.RUNNING)]
        self.sources = {
            KINDS[0]: queue.apply_approval_with_transition(self.jobs[0], approval_event_received=False)[1],
            KINDS[1]: queue.fail_job_safe(self.jobs[1], expected_job_id="running")[1],
            KINDS[2]: queue.complete_job(self.jobs[1], expected_job_id="running")[1],
            KINDS[3]: queue.assess_queue_blocked([job("paused", state=queue.WAITING_APPROVAL, requires_approval=True)]),
        }
        self.identity = queue.get_queue_identity()
        self.cp = checkpoint()
        self.before = self.snapshot()
        self.temp = tempfile.TemporaryDirectory(prefix="four-event-integration-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.path.write_text("[]\n", encoding="utf-8")
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1})
        for name in ("_default_transport", "load_credentials"):
            patcher = mock.patch.object(sender, name, side_effect=AssertionError("REAL_IO_FORBIDDEN"))
            self.addCleanup(patcher.stop)
            patched = patcher.start()
            self.addCleanup(patched.assert_not_called)

    def snapshot(self):
        return ([asdict(j) for j in self.jobs], {k: v.to_dict() for k, v in self.sources.items()},
                self.identity.to_dict(), self.cp.to_dict())

    def tearDown(self):
        self.assertEqual(self.before, self.snapshot())

    def dispatch(self, kind, mode="DRY_RUN"):
        options = dict(mode=mode, ledger=self.store, credential_loader=self.loader, transport=self.transport)
        if kind == "QUEUE_BLOCKED":
            return queue_dispatch.dispatch_queue_blocked(self.sources[kind], self.identity, **options)
        return job_dispatch.dispatch_transition(self.sources[kind], **options)

    def capture(self, kind):
        with mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as run:
            result = self.dispatch(kind)
        self.assertTrue(result.event_generated)
        self.assertTrue(result.runtime_handoff)
        return run.call_args.args[0]

    def test_version(self):
        self.assertEqual(INTEGRATED_VERSION, "0.1")

    def test_single_ledger_all_four(self):
        for index, kind in enumerate(KINDS, 1):
            self.assertEqual(self.dispatch(kind, "MOCK_RUNTIME").runtime_status, "NOTIFICATION_DELIVERED")
            self.assertEqual(recovery.inspect_ledger(self.store).record_count, index)
        saved = self.path.read_bytes()
        with mock.patch.object(sender, "_send", side_effect=AssertionError()) as send:
            for kind in KINDS:
                self.assertEqual(self.dispatch(kind, "MOCK_RUNTIME").runtime_status,
                                 "NOTIFICATION_DUPLICATE_SUPPRESSED")
        send.assert_not_called()
        self.assertEqual(saved, self.path.read_bytes())
        self.assertEqual(self.transport.call_count, 4)

    def test_adapter_matrix(self):
        expected = {KINDS[0]: (1, "IMMEDIATE"), KINDS[1]: (1, "IMMEDIATE"),
                    KINDS[2]: (0, "NORMAL"), KINDS[3]: (1, "IMMEDIATE")}
        for kind in KINDS:
            result = adapter.adapt_notification(self.capture(kind))
            self.assertEqual((result.pushover_priority, result.delivery_class), expected[kind])

    def test_validators_in_real_path(self):
        with mock.patch.object(queue, "validate_job_transition_result", wraps=queue.validate_job_transition_result) as jobs, \
             mock.patch.object(queue, "validate_queue_blocked_decision", wraps=queue.validate_queue_blocked_decision) as blocked, \
             mock.patch.object(queue, "validate_queue_identity", wraps=queue.validate_queue_identity) as identity, \
             mock.patch.object(queue, "build_queue_blocked_safe_event", wraps=queue.build_queue_blocked_safe_event) as factory:
            for kind in KINDS:
                self.dispatch(kind)
        self.assertEqual(jobs.call_count, 3)
        blocked.assert_called_once_with(self.sources[KINDS[3]])
        identity.assert_called()
        factory.assert_called_once_with(self.sources[KINDS[3]], self.identity)

    def test_critical_stop(self):
        result = runtime.process_notification(existing_event("CRITICAL_STOP"), mode="MOCK_RUNTIME",
            ledger=self.store, credential_loader=self.loader, transport=self.transport)
        self.assertEqual(result.runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.transport.assert_not_called()

    def test_approval_ready_suppressed(self):
        source = queue.apply_approval_with_transition(
            job(state=queue.WAITING_APPROVAL, requires_approval=True), approval_event_received=True)[1]
        with mock.patch.object(runtime, "process_notification") as run:
            result = job_dispatch.dispatch_transition(source)
        self.assertEqual(result.dispatch_status, "SUPPRESSED")
        self.assertFalse(result.event_generated)
        run.assert_not_called()

    def test_unknown_queue_no_event(self):
        source = queue.assess_queue_blocked([job(state=queue.CHECKPOINTED)])
        self.assertEqual(source.decision_status, "UNKNOWN")
        with mock.patch.object(runtime, "process_notification") as run:
            result = queue_dispatch.dispatch_queue_blocked(source, self.identity)
        self.assertFalse(result.event_generated)
        run.assert_not_called()

    def test_idle_queue_no_event(self):
        with mock.patch.object(runtime, "process_notification") as run:
            result = queue_dispatch.dispatch_queue_blocked(queue.assess_queue_blocked([]), self.identity)
        self.assertFalse(result.event_generated)
        run.assert_not_called()

    def test_production_ledger_read_only(self):
        saved = ledger.DEFAULT_PATH.read_bytes()
        for kind in KINDS:
            self.dispatch(kind)
            self.dispatch(kind, "MOCK_RUNTIME")
        self.assertEqual(saved, ledger.DEFAULT_PATH.read_bytes())


def event_case(kind, scenario):
    def test(self):
        if scenario == "dry":
            saved = self.path.read_bytes()
            first, second = self.capture(kind), self.capture(kind)
            self.assertEqual(first, second)
            self.assertEqual(runtime.event_identity(first), runtime.event_identity(second))
            self.assertEqual(self.dispatch(kind).runtime_status, "NOTIFICATION_READY")
            self.transport.assert_not_called()
            self.assertEqual(saved, self.path.read_bytes())
        elif scenario == "first":
            self.assertEqual(self.dispatch(kind, "MOCK_RUNTIME").runtime_status, "NOTIFICATION_DELIVERED")
            self.assertEqual(recovery.inspect_ledger(self.store).record_count, 1)
            self.transport.assert_called_once()
        else:
            self.dispatch(kind, "MOCK_RUNTIME")
            saved = self.path.read_bytes()
            self.transport.reset_mock()
            with mock.patch.object(sender, "_send", side_effect=AssertionError()) as send:
                result = self.dispatch(kind, "MOCK_RUNTIME")
            self.assertEqual(result.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
            send.assert_not_called()
            self.transport.assert_not_called()
            self.assertEqual(saved, self.path.read_bytes())
    return test


for _kind in KINDS:
    for _scenario in ("dry", "first", "duplicate"):
        setattr(FourEventIntegrationTests, "test_" + _kind + "_" + _scenario, event_case(_kind, _scenario))


def pair_case(left, right):
    def test(self):
        self.assertNotEqual(runtime.event_identity(self.capture(left)), runtime.event_identity(self.capture(right)))
    return test


for _left, _right in combinations(KINDS, 2):
    setattr(FourEventIntegrationTests, "test_pair_" + _left + _right, pair_case(_left, _right))


def failure_case(kind, component):
    def test(self):
        target, name, error = {
            "runtime": (runtime, "process_notification", ValueError("fixture-failure")),
            "sender": (sender, "_send", ValueError("fixture-failure")),
            "ledger": (ledger.NotificationLedger, "_replace", ledger.LedgerError("LEDGER_WRITE_FAILED")),
        }[component]
        with mock.patch.object(target, name, side_effect=error):
            result = self.dispatch(kind, "MOCK_RUNTIME")
        self.assertEqual(result.dispatch_status, "FAILED_SAFE")
        self.assertEqual(self.before, self.snapshot())
    return test


for _kind in ("JOB_COMPLETED", "QUEUE_BLOCKED"):
    for _component in ("runtime", "sender", "ledger"):
        setattr(FourEventIntegrationTests, "test_failure_" + _kind + _component, failure_case(_kind, _component))


def suppressed_case(kind):
    def test(self):
        result = runtime.process_notification(existing_event(kind), mode="MOCK_RUNTIME", ledger=self.store,
                                             credential_loader=self.loader, transport=self.transport)
        self.assertEqual(result.runtime_status, "NOTIFICATION_SUPPRESSED")
        self.transport.assert_not_called()
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 0)
    return test


for _kind in ("JOB_STARTED", "JOB_CHECKPOINTED", "JOB_SWITCHED", "QUEUE_IDLE"):
    setattr(FourEventIntegrationTests, "test_suppressed_" + _kind, suppressed_case(_kind))


if __name__ == "__main__":
    unittest.main()
