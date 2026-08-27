import ast
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import job_level_event_dispatch as dispatch
import unattended_job_queue as queue
import unattended_runtime as runtime
import notification_ledger as ledger
import ledger_recovery as recovery
import pushover_sender as sender
import pushover_notification_adapter as adapter
from tests.test_unattended_job_queue import job, checkpoint
from tests.test_unattended_runtime import event as regression_event


class JobLevelDispatchTests(unittest.TestCase):
    def setUp(self):
        self.running = job(state=queue.RUNNING)
        self.sources = {
            "waiting": queue.apply_approval_with_transition(job(requires_approval=True), approval_event_received=False)[1],
            "failed": queue.fail_job_safe(self.running, expected_job_id="job-a")[1],
            "completed": queue.complete_job(self.running, expected_job_id="job-a")[1],
        }
        self.temp = tempfile.TemporaryDirectory(prefix="job-dispatch-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.path.write_bytes(b"[]\n")
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-private-response"})
        for name in ("_default_transport", "load_credentials"):
            patcher = mock.patch.object(sender, name, side_effect=AssertionError("REAL_IO_FORBIDDEN"))
            self.addCleanup(patcher.stop)
            patched = patcher.start()
            self.addCleanup(patched.assert_not_called)

    def execute(self, source=None, **kwargs):
        options = dict(mode="MOCK_RUNTIME", ledger=self.store,
                       credential_loader=self.loader, transport=self.transport)
        options.update(kwargs)
        return dispatch.dispatch_transition(self.sources["completed"] if source is None else source, **options)

    def test_version_schema(self):
        result = self.execute()
        self.assertEqual(result.dispatch_version, "0.1")
        self.assertEqual(len(result.to_dict()), 10)

    def test_validator_first(self):
        order = []
        original = queue.validate_job_transition_result
        def validate(value):
            order.append("validate")
            return original(value)
        def run(*args, **kwargs):
            order.append("runtime")
            raise RuntimeError()
        with mock.patch.object(queue, "validate_job_transition_result", side_effect=validate) as checked, mock.patch.object(runtime, "process_notification", side_effect=run):
            self.execute()
        checked.assert_called_once_with(self.sources["completed"])
        self.assertEqual(order, ["validate", "runtime"])

    def test_invalid_validator_outputs(self):
        good = queue.validate_job_transition_result(self.sources["completed"])
        for value in (None, {}, replace(good, valid=False), replace(good, valid=1),
                      replace(good, transition_class="fixture-secret"), replace(good, validation_version="9"),
                      replace(good, reason_code="fixture-secret")):
            with mock.patch.object(queue, "validate_job_transition_result", return_value=value), mock.patch.object(runtime, "process_notification") as run:
                result = self.execute()
            self.assertFalse(result.event_generated)
            run.assert_not_called()
            self.assertNotIn("fixture-secret", json.dumps(result.to_dict()))

    def test_validator_exception(self):
        with mock.patch.object(queue, "validate_job_transition_result", side_effect=ValueError("fixture-secret")), mock.patch.object(runtime, "process_notification") as run:
            result = self.execute()
        run.assert_not_called()
        self.assertFalse(result.event_generated)
        self.assertNotIn("fixture-secret", repr(result))

    def test_non_transition_sources_rejected(self):
        for source in (None, {}, "fixture-secret", self.running, queue.select_next_job([])):
            with mock.patch.object(runtime, "process_notification") as run:
                result = dispatch.dispatch_transition(source)
            self.assertFalse(result.event_generated)
            run.assert_not_called()

    def test_runtime_unknown_status_sanitized(self):
        bad = runtime.RuntimeResult("0.1", "MOCK_RUNTIME", "fixture-secret", "JOB_COMPLETED",
                                    True, False, False, False, False, False, ())
        with mock.patch.object(runtime, "process_notification", return_value=bad):
            result = self.execute()
        self.assertEqual(result.reason_code, "RUNTIME_RESULT_INVALID")
        self.assertNotIn("fixture-secret", repr(result))

    def test_approval_ready_suppressed(self):
        source = queue.apply_approval_with_transition(job(state=queue.WAITING_APPROVAL, requires_approval=True), approval_event_received=True)[1]
        with mock.patch.object(runtime, "process_notification") as run:
            result = self.execute(source)
        self.assertEqual(result.dispatch_status, "SUPPRESSED")
        self.assertFalse(result.event_generated)
        run.assert_not_called()

    def test_no_second_transition_validator(self):
        tree = ast.parse(Path(dispatch.__file__).read_text(encoding="utf-8"))
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn("previous_state", attrs)
        self.assertNotIn("fromisoformat", attrs)
        self.assertNotIn("now", attrs)
        self.assertNotIn("sha256", attrs)
        imports = {n.names[0].name for n in tree.body if isinstance(n, ast.Import)}
        self.assertEqual(imports, {"unattended_job_queue", "unattended_runtime"})
        # Source reason/version are never read; only the Core validation response is inspected.
        forbidden = {"reason_code", "transition_version", "previous_state"}
        self.assertFalse(any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                             and n.value.id == "source" and n.attr in forbidden for n in ast.walk(tree)))

    def test_live_and_unknown_modes_block(self):
        for mode in ("LIVE_NOTIFICATION", "UNKNOWN", None, []):
            with mock.patch.object(runtime, "process_notification") as run:
                result = self.execute(mode=mode)
            self.assertEqual(result.dispatch_status, "BLOCKED")
            self.assertFalse(result.event_generated)
            run.assert_not_called()

    def test_mock_requires_fixtures(self):
        result = dispatch.dispatch_transition(self.sources["completed"], mode="MOCK_RUNTIME")
        self.assertFalse(result.runtime_handoff)

    def test_mock_production_store_rejected(self):
        before = ledger.DEFAULT_PATH.read_bytes() if ledger.DEFAULT_PATH.exists() else None
        result = self.execute(ledger=ledger.NotificationLedger())
        self.assertEqual(result.dispatch_status, "FAILED_SAFE")
        self.transport.assert_not_called()
        self.assertEqual(before, ledger.DEFAULT_PATH.read_bytes() if ledger.DEFAULT_PATH.exists() else None)

    def test_core_mapping_is_only_source(self):
        # A conforming direct construction is accepted: no origin authentication.
        source = queue.JobTransitionResult(**self.sources["completed"].to_dict())
        self.assertEqual(self.execute(source).event_type, "JOB_COMPLETED")

    def test_identity_and_timestamp(self):
        for source in self.sources.values():
            with mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as run, mock.patch.object(queue, "datetime", wraps=datetime) as clock:
                self.execute(source, mode="DRY_RUN")
                first = run.call_args.args[0]
                self.execute(source, mode="DRY_RUN")
                second = run.call_args.args[0]
                clock.now.assert_not_called()
            self.assertEqual(first, second)
            self.assertEqual(first["occurred_at"], source.occurred_at)
            self.assertEqual(runtime.event_identity(first), runtime.event_identity(second))

    def test_cross_event_identity(self):
        identities = set()
        for source in self.sources.values():
            with mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as run:
                self.execute(source, mode="DRY_RUN")
            identities.add(runtime.event_identity(run.call_args.args[0]))
        self.assertEqual(len(identities), 3)

    def test_runtime_exception_isolation(self):
        source = self.sources["completed"]
        before = source.to_dict()
        with mock.patch.object(runtime, "process_notification", side_effect=ValueError("fixture-secret")):
            result = self.execute(source)
        self.assertEqual(result.dispatch_status, "FAILED_SAFE")
        self.assertTrue(result.runtime_handoff)
        self.assertEqual(source.to_dict(), before)
        self.assertNotIn("fixture-secret", repr(result))

    def test_bad_runtime_output(self):
        with mock.patch.object(runtime, "process_notification", return_value={"raw": "fixture-secret"}):
            result = self.execute()
        self.assertEqual(result.reason_code, "RUNTIME_RESULT_INVALID")
        self.assertNotIn("fixture-secret", repr(result))

    def test_no_queue_mutators(self):
        cp = checkpoint()
        before = cp.to_dict()
        with mock.patch.object(queue, "apply_approval", side_effect=AssertionError()), mock.patch.object(queue, "complete_job", side_effect=AssertionError()), mock.patch.object(queue, "fail_job_safe", side_effect=AssertionError()), mock.patch.object(queue, "assess_retry", side_effect=AssertionError()), mock.patch.object(queue, "select_next_job", side_effect=AssertionError()):
            self.assertEqual(self.execute().dispatch_status, "COMPLETED")
        self.assertEqual(before, cp.to_dict())
        self.assertEqual(self.running.state, queue.RUNNING)

    def test_protected_files(self):
        paths = [ROOT / ".env", ledger.DEFAULT_PATH, ROOT / "data/data-lab.db"]
        def digest(p):
            return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        before = [digest(p) for p in paths]
        for source in self.sources.values():
            self.execute(source, mode="DRY_RUN", ledger=None)
        self.assertEqual(before, [digest(p) for p in paths])
        self.transport.assert_not_called()

    def test_critical_negative_invariant(self):
        result = runtime.process_notification(regression_event("CRITICAL_STOP"), mode="MOCK_RUNTIME",
            ledger=self.store, credential_loader=self.loader, transport=self.transport)
        self.assertEqual(result.runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.transport.assert_not_called()


def case(kind, scenario):
    def test(self):
        source = self.sources[kind]
        before = source.to_dict()
        if scenario == "dry":
            result = self.execute(source, mode="DRY_RUN")
            self.assertEqual(result.runtime_status, "NOTIFICATION_READY")
            self.transport.assert_not_called()
            self.assertEqual(self.path.read_bytes(), b"[]\n")
        elif scenario == "mock":
            with mock.patch.object(adapter, "_adapt", wraps=adapter._adapt) as adapt, mock.patch.object(sender, "_send", wraps=sender._send) as send, mock.patch.object(runtime, "inspect_ledger", wraps=runtime.inspect_ledger) as inspect:
                result = self.execute(source)
            self.assertEqual(result.event_type, {"waiting": "JOB_WAITING_APPROVAL", "failed": "JOB_FAILED_SAFE", "completed": "JOB_COMPLETED"}[kind])
            self.assertEqual(result.runtime_status, "NOTIFICATION_DELIVERED")
            adapt.assert_called_once(); send.assert_called_once(); inspect.assert_called_once()
            self.assertEqual(self.transport.call_args.args[1]["priority"], 0 if kind == "completed" else 1)
            self.assertEqual(recovery.inspect_ledger(self.store).record_count, 1)
        elif scenario == "duplicate":
            self.execute(source)
            saved = self.path.read_bytes()
            self.transport.reset_mock(); self.loader.reset_mock()
            with mock.patch.object(sender, "_send", wraps=sender._send) as send:
                result = self.execute(source)
            self.assertEqual(result.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
            send.assert_not_called(); self.transport.assert_not_called(); self.loader.assert_not_called()
            self.assertEqual(saved, self.path.read_bytes())
        elif scenario == "sender_failure":
            self.transport.side_effect = TimeoutError("fixture-secret")
            result = self.execute(source)
            self.assertEqual(result.dispatch_status, "FAILED_SAFE")
            self.assertEqual(self.path.read_bytes(), b"[]\n")
            self.assertNotIn("fixture-secret", repr(result))
        elif scenario == "ledger_failure":
            with mock.patch.object(ledger.NotificationLedger, "_replace", side_effect=ledger.LedgerError("LEDGER_WRITE_FAILED")):
                result = self.execute(source)
            self.assertEqual(result.dispatch_status, "FAILED_SAFE")
            self.assertEqual(self.path.read_bytes(), b"[]\n")
        elif scenario == "recovery_block":
            self.path.write_bytes(b"broken")
            result = self.execute(source)
            self.assertEqual(result.dispatch_status, "FAILED_SAFE")
            self.transport.assert_not_called()
        elif scenario == "safe_output":
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                result = self.execute(source)
            self.assertEqual(out.getvalue(), "")
            serialized = json.dumps(result.to_dict())
            self.assertNotIn(self.transport.call_args.args[1]["message"], serialized)
            for secret in ("fixture-user", "fixture-app", "fixture-private-response", "http", "payload", "traceback"):
                self.assertNotIn(secret, serialized)
        self.assertEqual(before, source.to_dict())
    return test


for _kind in ("waiting", "failed", "completed"):
    for _scenario in ("dry", "mock", "duplicate", "sender_failure", "ledger_failure", "recovery_block", "safe_output"):
        setattr(JobLevelDispatchTests, "test_" + _kind + "_" + _scenario, case(_kind, _scenario))


def invalid_case(change):
    def test(self):
        source = replace(self.sources["completed"], **change)
        with mock.patch.object(runtime, "process_notification") as run:
            result = self.execute(source)
        self.assertFalse(result.event_generated)
        run.assert_not_called()
    return test


for _name, _change in {
    "rejected": {"transition_status": "REJECTED"}, "ready_done": {"previous_state": queue.READY},
    "id_missing": {"job_id": ""}, "version": {"transition_version": "9"},
    "time": {"occurred_at": "bad"}, "reason": {"reason_code": "UNKNOWN"},
    "queue_idle": {"new_state": "QUEUE_IDLE"}, "queue_blocked": {"new_state": "QUEUE_BLOCKED"},
    "critical": {"new_state": "CRITICAL_STOP"},
}.items():
    setattr(JobLevelDispatchTests, "test_invalid_" + _name, invalid_case(_change))


if __name__ == "__main__":
    unittest.main()
