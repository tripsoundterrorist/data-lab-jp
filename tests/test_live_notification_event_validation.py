"""LIVE-mode simulation only: real pipeline, isolated ledger, fake transport."""

import ast
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import live_notification_event_validation as expansion
import scheduled_runtime_live_canary as bridge
import unattended_runtime as runtime
import pushover_notification_adapter as adapter
import pushover_sender as sender
import notification_ledger as ledger
import ledger_recovery as recovery
from tests.test_unattended_runtime import event as existing_event


EXPECTED = {
    "JOB_FAILED_SAFE": (1, "IMMEDIATE"),
    "QUEUE_BLOCKED": (1, "IMMEDIATE"),
    "JOB_COMPLETED": (0, "NORMAL"),
}


class EventExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="event-expansion-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.path.write_bytes(b"[]\n")
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-private-response"})
        self.adapt = mock.Mock(wraps=adapter.adapt_notification)
        self.send = mock.Mock(wraps=sender.send_notification)
        # Any accidental fallback to real transport or credentials is a test failure.
        for name in ("_default_transport", "load_credentials"):
            patcher = mock.patch.object(sender, name, side_effect=AssertionError("REAL_IO_FORBIDDEN"))
            self.addCleanup(patcher.stop)
            patched = patcher.start()
            self.addCleanup(patched.assert_not_called)

    def execute(self, value, **overrides):
        kwargs = dict(mode="LIVE_NOTIFICATION", live_notification_confirmed=True,
                      ledger=self.store, credential_loader=self.loader,
                      transport=self.transport, adapter_fn=self.adapt, sender_fn=self.send)
        kwargs.update(overrides)
        return runtime.process_notification(value, **kwargs)

    def assert_empty(self):
        self.assertEqual(self.path.read_bytes(), b"[]\n")
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 0)

    def test_version(self):
        self.assertEqual(expansion.EXPANSION_VERSION, "0.1")

    def test_allowlist(self):
        self.assertEqual(expansion.EVENT_TYPES, frozenset(EXPECTED))
        for value in (None, {}, [], 1, "CRITICAL_STOP", "JOB_WAITING_APPROVAL",
                      "JOB_STARTED", "JOB_CHECKPOINTED", "JOB_SWITCHED", "QUEUE_IDLE", "fixture-secret"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "^EXPANSION_EVENT_NOT_ALLOWED$"):
                expansion.fixture_event(value)

    def test_no_overrides(self):
        for key in ("job_id", "priority", "payload", "identity", "ledger", "sender", "occurred_at"):
            with self.subTest(key=key), self.assertRaises(TypeError):
                expansion.fixture_event("JOB_COMPLETED", **{key: None})

    def test_fixture_has_no_execution_dependencies(self):
        tree = ast.parse(Path(expansion.__file__).read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)))
        calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertEqual(set(calls), {"frozenset", "type", "ValueError"})
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) for n in ast.walk(tree)))

    def test_fixture_generation_no_io(self):
        with mock.patch("builtins.open", side_effect=AssertionError()), mock.patch.object(
                Path, "open", side_effect=AssertionError()):
            for kind in EXPECTED:
                expansion.fixture_event(kind)

    def test_cross_event_identity(self):
        events = [expansion.fixture_event(kind) for kind in EXPECTED]
        self.assertEqual(len({e["job_id"] for e in events}), 1)
        identities = [runtime.event_identity(e) for e in events]
        self.assertEqual(len(set(identities)), 3)
        # Hold every other identity input equal to prove event_type participation.
        base = events[0]
        self.assertEqual(len({runtime.event_identity(dict(base, event_type=k)) for k in EXPECTED}), 3)

    def test_identity_across_processes(self):
        code = ('import sys,json;sys.path.insert(0,"scripts");'
                'import live_notification_event_validation as e;import unattended_runtime as r;'
                'print(json.dumps({k:r.event_identity(e.fixture_event(k)) for k in sorted(e.EVENT_TYPES)}))')
        result = subprocess.check_output([sys.executable, "-B", "-c", code], cwd=ROOT, text=True)
        self.assertEqual(json.loads(result), {k: runtime.event_identity(expansion.fixture_event(k)) for k in EXPECTED})

    def test_three_events_share_ledger(self):
        for count, kind in enumerate(EXPECTED, 1):
            self.assertTrue(self.execute(expansion.fixture_event(kind)).delivery_succeeded)
            self.assertEqual(recovery.inspect_ledger(self.store).record_count, count)
        for kind in EXPECTED:
            self.assertEqual(self.execute(expansion.fixture_event(kind)).runtime_status,
                             "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.assertEqual(self.transport.call_count, 3)
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 3)

    def test_suppression_matrix(self):
        for kind in ("JOB_STARTED", "JOB_CHECKPOINTED", "JOB_SWITCHED", "QUEUE_IDLE"):
            result = self.execute(existing_event(kind))
            self.assertEqual(result.runtime_status, "NOTIFICATION_SUPPRESSED")
            self.assertFalse(result.delivery_attempted)
        self.adapt.assert_not_called()
        self.send.assert_not_called()
        self.assert_empty()

    def test_critical_stop_negative_invariant(self):
        # Existing regression fixture only; expansion cannot generate this event.
        value = existing_event("CRITICAL_STOP")
        a = adapter.adapt_notification(value)
        self.assertEqual(a.pushover_priority, 2)
        self.assertTrue(a.emergency_candidate)
        result = self.execute(value)
        self.assertEqual(result.runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.assertFalse(result.delivery_attempted)
        self.transport.assert_not_called()
        self.assert_empty()

    def test_bridge_unchanged_contract(self):
        self.assertEqual(bridge.canary_event()["event_type"], "JOB_WAITING_APPROVAL")
        with mock.patch.object(bridge.runner, "run_once") as run, mock.patch("sys.stdout", new_callable=io.StringIO):
            for kind in EXPECTED:
                self.assertEqual(bridge.main([bridge.CONFIRMATION, "--event-type", kind]), 2)
        run.assert_not_called()

    def test_production_files_read_only(self):
        paths = [ledger.DEFAULT_PATH, ROOT / ".env", ROOT / "data/data-lab.db"]
        paths += sorted((ROOT / "logs/probes/state").glob("*"))
        paths += sorted(p for p in (ROOT / "dist").rglob("*") if p.is_file())
        def digest(path):
            return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        before = {str(p): digest(p) for p in paths}
        for kind in EXPECTED:
            self.execute(expansion.fixture_event(kind))
        self.assertEqual(before, {str(p): digest(p) for p in paths})


def event_case(kind, check):
    def test(self):
        value = expansion.fixture_event(kind)
        if check == "schema":
            self.assertEqual(set(value), runtime.EVENT_FIELDS)
            self.assertEqual(runtime._validate_event(value)[1], ())
            self.assertIn(kind, runtime.AUTO_NOTIFY_EVENTS)
            self.assertFalse(value["approval_required"])
        elif check == "identity":
            first = runtime.event_identity(value)
            self.assertIsNotNone(first)
            self.assertEqual(first, runtime.event_identity(expansion.fixture_event(kind)))
            with mock.patch.object(runtime, "event_identity", wraps=runtime.event_identity) as identity:
                self.execute(value)
            identity.assert_called_once_with(value)
        elif check == "policy":
            a = adapter.adapt_notification(value)
            self.assertEqual((a.pushover_priority, a.delivery_class), EXPECTED[kind])
            self.assertFalse(a.emergency_candidate)
            self.assertEqual(self.execute(value).runtime_status, "NOTIFICATION_DELIVERED")
            self.adapt.assert_called_once_with(value)
            self.send.assert_called_once()
            actual = self.send.call_args.args[0]
            self.assertEqual(actual, a)
            payload = self.transport.call_args.args[1]
            self.assertEqual(payload["priority"], EXPECTED[kind][0])
            self.assertEqual(payload["message"], a.message)
        elif check == "success":
            self.assert_empty()
            result = self.execute(value)
            self.assertTrue(result.delivery_succeeded)
            self.assertEqual(result.runtime_status, "NOTIFICATION_DELIVERED")
            report = recovery.inspect_ledger(self.store)
            self.assertEqual(report.record_count, 1)
            rows = json.loads(self.path.read_bytes())
            self.assertEqual(rows[0]["event_identity"], runtime.event_identity(value))
            self.assertEqual(rows[0]["event_type"], kind)
        elif check == "duplicate":
            self.execute(value)
            before = self.path.read_bytes()
            self.adapt.reset_mock(); self.send.reset_mock(); self.loader.reset_mock(); self.transport.reset_mock()
            result = self.execute(expansion.fixture_event(kind))
            self.assertEqual(result.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
            self.assertFalse(result.delivery_attempted)
            self.adapt.assert_not_called(); self.send.assert_not_called()
            self.loader.assert_not_called(); self.transport.assert_not_called()
            self.assertEqual(before, self.path.read_bytes())
        elif check in {"rejected", "exception", "timeout", "delivery_false"}:
            if check == "rejected":
                self.transport.return_value = {"status": 0, "errors": ["fixture-private-response"]}
            elif check == "exception":
                self.send.side_effect = RuntimeError("fixture-secret")
            elif check == "timeout":
                self.transport.side_effect = TimeoutError("fixture-secret")
            else:
                self.send = mock.Mock(return_value=sender.SenderResult(
                    "0.1", "LIVE_SEND", "SEND_FAILED_SAFE", True, False, False, False, True, ("SAFE_FAILURE",)))
            result = self.execute(value)
            self.assertFalse(result.delivery_succeeded)
            self.assertEqual(result.runtime_status, "NOTIFICATION_FAILED_SAFE")
            self.assert_empty()
            self.assertLessEqual(self.transport.call_count, 1)
            self.assertNotIn("fixture-secret", json.dumps(result.to_dict()))
        elif check == "mutation":
            before = deepcopy(value)
            self.execute(value)
            self.assertEqual(value, before)
            value["job_id"] = "changed"
            self.assertEqual(expansion.fixture_event(kind), before)
        elif check == "safe_output":
            with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                result = self.execute(value)
            self.assertEqual(output.getvalue(), "")
            text = json.dumps(result.to_dict())
            for forbidden in ("fixture-user", "fixture-app", "fixture-private-response", "http", "payload", "traceback",
                              adapter.adapt_notification(value).message):
                self.assertNotIn(forbidden, text)
        elif check == "missing_gate":
            self.path.unlink()
            result = self.execute(value)
            self.assertFalse(result.delivery_attempted)
            self.send.assert_not_called()
            self.assertFalse(self.path.exists())
    return test


for _kind in EXPECTED:
    for _check in ("schema", "identity", "policy", "success", "duplicate", "rejected",
                   "exception", "timeout", "delivery_false", "mutation", "safe_output", "missing_gate"):
        setattr(EventExpansionTests, "test_" + _kind.lower() + "_" + _check, event_case(_kind, _check))


if __name__ == "__main__":
    unittest.main()
