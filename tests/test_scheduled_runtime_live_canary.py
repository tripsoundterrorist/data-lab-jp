import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scheduled_runtime_live_canary as bridge
import scheduled_runtime_runner as runner
import unattended_runtime as runtime
import notification_ledger as ledger
import ledger_recovery as recovery


class CanaryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="canary-bridge-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.path.write_bytes(b"[]\n")
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-private-response"})
        original = runner.run_once
        self.call = mock.Mock(side_effect=lambda event, **kw: original(
            event, **kw, ledger=self.store, credential_loader=self.loader,
            transport=self.transport, lock_path=Path(self.temp.name) / "runner.lock"))
        self.patch = mock.patch.object(runner, "run_once", self.call)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def execute(self):
        return bridge.run_canary(confirmed=True)

    def test_version(self):
        self.assertEqual(bridge.BRIDGE_VERSION, "0.1")

    def test_exact_event(self):
        event = bridge.canary_event()
        self.assertEqual(set(event), runtime.EVENT_FIELDS)
        self.assertEqual(event["event_type"], "JOB_WAITING_APPROVAL")
        self.assertTrue(event["approval_required"])
        self.assertEqual(runtime._validate_event(event)[1], ())

    def test_fresh_fixed_event(self):
        first = bridge.canary_event()
        first["job_id"] = "changed"
        self.assertNotEqual(first, bridge.canary_event())
        self.assertEqual(bridge.canary_event(), bridge.canary_event())

    def test_identity_stable(self):
        self.assertEqual(runtime.event_identity(bridge.canary_event()),
                         runtime.event_identity(bridge.canary_event()))

    def test_identity_reused(self):
        with mock.patch.object(runtime, "event_identity", wraps=runtime.event_identity) as identity:
            self.execute()
        identity.assert_called_once_with(bridge.canary_event())

    def test_confirmation_required(self):
        for value in (False, None, 1, "true"):
            self.assertEqual(bridge.run_canary(confirmed=value)["exit_code"], 2)
        self.call.assert_not_called()

    def test_cli_misuse(self):
        for args in ([], ["--mode", "LIVE_NOTIFICATION"], *(
                [bridge.CONFIRMATION, key, "fixture-secret"] for key in (
                    "--event-type", "--job-id", "--priority", "--payload", "--message",
                    "--identity", "--identity-seed", "--ledger", "--sender", "--skip-recovery"))):
            with self.subTest(args=args), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(bridge.main(args), 2)
                self.assertNotIn("fixture-secret", out.getvalue())
        self.call.assert_not_called()

    def test_internal_event_override_rejected(self):
        with self.assertRaises(TypeError):
            bridge.run_canary(event={})

    def test_cli_confirmed(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(bridge.main([bridge.CONFIRMATION]), 0)
        self.assertEqual(json.loads(out.getvalue())["bridge_status"], "COMPLETED")
        self.call.assert_called_once_with(bridge.canary_event(), mode="LIVE_NOTIFICATION",
                                          live_notification_confirmed=True)

    def test_delivery_and_duplicate(self):
        first = self.execute()
        self.assertEqual(first["runtime_status"], "NOTIFICATION_DELIVERED")
        self.assertTrue(first["notification_attempted"])
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 1)
        before = self.path.read_bytes()
        second = self.execute()
        self.assertTrue(second["duplicate_suppressed"])
        self.assertFalse(second["notification_attempted"])
        self.assertEqual(second["exit_code"], 0)
        self.assertEqual(before, self.path.read_bytes())
        self.loader.assert_called_once()
        self.transport.assert_called_once()

    def test_adapter_policy(self):
        with mock.patch.object(runtime.notification_adapter, "_adapt",
                               wraps=runtime.notification_adapter._adapt) as adapt:
            self.execute()
        adapt.assert_called_once()
        payload = self.transport.call_args.args[1]
        self.assertEqual(payload["priority"], 1)
        self.assertNotIn("retry", payload)
        adapted = runtime.notification_adapter.adapt_notification(bridge.canary_event())
        self.assertEqual(adapted.delivery_class, "IMMEDIATE")
        self.assertFalse(adapted.emergency_candidate)

    def test_missing(self):
        self.path.unlink()
        self.assertEqual(self.execute()["recovery_status"], "RECOVERABLE_NO_WRITE")
        self.assertFalse(self.path.exists())
        self.transport.assert_not_called()

    def test_corruption(self):
        self.path.write_bytes(b"broken")
        self.assertEqual(self.execute()["recovery_status"], "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(self.path.read_bytes(), b"broken")
        self.transport.assert_not_called()

    def test_recovery_states(self):
        for state in ("RECOVERY_BLOCKED", "MANUAL_REVIEW_REQUIRED", "RECOVERABLE_NO_WRITE", "UNKNOWN"):
            with self.subTest(state=state), mock.patch.object(
                    recovery, "inspect_ledger", return_value=recovery.RecoveryReport(recovery_status=state)):
                result = self.execute()
                self.assertEqual(result["exit_code"], 2)
                self.assertFalse(result["runtime_invoked"])
        self.transport.assert_not_called()

    def test_recovery_exception(self):
        with mock.patch.object(recovery, "inspect_ledger", side_effect=RuntimeError("fixture-secret")):
            result = self.execute()
        self.assertEqual(result["exit_code"], 3)
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.transport.assert_not_called()

    def test_root_failure(self):
        with mock.patch.object(runner, "resolve_repository_root", side_effect=ValueError("fixture-secret")):
            self.assertEqual(self.execute()["exit_code"], 3)
        self.call.assert_not_called()

    def test_runner_exception_uncertain(self):
        self.call.side_effect = RuntimeError("fixture-secret")
        result = self.execute()
        self.assertIsNone(result["notification_attempted"])
        self.assertNotIn("fixture-secret", json.dumps(result))

    def test_invalid_result(self):
        self.call.side_effect = None
        self.call.return_value = {"raw": "fixture-secret"}
        self.assertEqual(self.execute()["exit_code"], 3)

    def test_result_field_injection(self):
        valid = self.call(bridge.canary_event(), mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.call.side_effect = None
        for field in ("runner_status", "runtime_status", "recovery_status"):
            self.call.return_value = dataclasses.replace(valid, **{field: "fixture-secret"})
            result = self.execute()
            self.assertEqual(result["exit_code"], 3)
            self.assertNotIn("fixture-secret", json.dumps(result))

    def test_output_safe(self):
        text = json.dumps(self.execute())
        for forbidden in ("fixture-user", "fixture-app", "fixture-private-response", "payload", "http", "traceback"):
            self.assertNotIn(forbidden, text)

    def test_send_failure_no_record(self):
        self.transport.side_effect = RuntimeError("fixture-secret")
        result = self.execute()
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(self.path.read_bytes(), b"[]\n")
        self.assertNotIn("fixture-secret", json.dumps(result))

    def test_protected_files(self):
        paths = [ROOT / ".env", ledger.DEFAULT_PATH]
        def digest(p):
            return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        before = [digest(p) for p in paths]
        self.execute()
        self.assertEqual(before, [digest(p) for p in paths])

    def test_no_queue_approval_calls(self):
        with mock.patch.object(runtime.queue, "create_event", wraps=runtime.queue.create_event) as create:
            self.execute()
        create.assert_called_once_with(**bridge.canary_event())
        # The only queue hook is the pure contract validator, not a persisted job.

    def test_environment_not_confirmation(self):
        with mock.patch.dict(os.environ, {"RUNNER_MODE": "LIVE_NOTIFICATION"}), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(bridge.main([]), 2)
        self.call.assert_not_called()

    def test_original_cli_rejects_live(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(runner.main(["--mode", "LIVE_NOTIFICATION"]), 2)
        self.call.assert_not_called()

    def test_subprocess_cli_rejects(self):
        completed = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/scheduled_runtime_live_canary.py"),
                                    "--priority", "2"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["notification_attempted"], False)

    def test_cross_process_identity(self):
        code = ('import sys;sys.path.insert(0,"scripts");'
                'import scheduled_runtime_live_canary as b;import unattended_runtime as r;'
                'print(r.event_identity(b.canary_event()))')
        value = subprocess.check_output([sys.executable, "-B", "-c", code], cwd=ROOT, text=True).strip()
        self.assertEqual(value, runtime.event_identity(bridge.canary_event()))

    def test_canary_generation_no_io(self):
        with mock.patch("builtins.open", side_effect=AssertionError()), mock.patch.object(
                Path, "open", side_effect=AssertionError()):
            self.assertEqual(bridge.canary_event()["state"], "WAITING_APPROVAL")

    def test_no_internal_overrides(self):
        for key in ("event", "priority", "payload", "identity", "ledger", "transport", "recovery"):
            with self.subTest(key=key), self.assertRaises(TypeError):
                bridge.run_canary(confirmed=True, **{key: None})
        self.call.assert_not_called()

    def test_output_fields(self):
        self.assertEqual(set(self.execute()), {
            "bridge_version", "bridge_status", "canary_type", "runner_mode",
            "recovery_status", "runtime_invoked", "notification_attempted",
            "runtime_status", "duplicate_suppressed", "exit_code", "reason_codes"})

    def test_no_credential_loader_before_recovery(self):
        self.path.unlink()
        self.execute()
        self.loader.assert_not_called()
        self.transport.assert_not_called()

    def test_ledger_busy(self):
        self.path.with_name(self.path.name + ".lock").write_bytes(b"")
        self.assertEqual(self.execute()["exit_code"], 2)
        self.transport.assert_not_called()

    def test_temp_artifact_blocks(self):
        self.path.with_name(self.path.name + ".test.tmp").write_bytes(b"[]\n")
        self.assertEqual(self.execute()["exit_code"], 2)
        self.transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
