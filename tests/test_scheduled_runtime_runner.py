from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scheduled_runtime_runner as runner
import ledger_recovery as recovery
import notification_ledger as ledger
import unattended_runtime as runtime
from tests.test_notification_ledger import event


class ScheduledRuntimeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scheduled-runner-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.store = ledger.NotificationLedger(self.path)
        self.lock = Path(self.temp.name) / "runner.lock"
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-response"})
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))

    def execute(self, value=None, **kwargs):
        options = dict(ledger=self.store, lock_path=self.lock,
                       credential_loader=self.loader, transport=self.transport)
        options.update(kwargs)
        return runner.run_once(value, **options)

    def healthy(self):
        self.path.write_text("[]\n", encoding="utf-8")

    def test_default_dry(self):
        self.assertEqual(self.execute().mode, "DRY_RUN")

    def test_no_argument_cli(self):
        with mock.patch.object(runner, "runner_lock_path", return_value=self.lock), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(runner.main([]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["mode"], "DRY_RUN")
            self.assertFalse(result["runtime_invoked"])

    def test_dry_no_send(self):
        self.assertEqual(self.execute(event()).exit_code, 0)
        self.transport.assert_not_called()

    def test_dry_no_ledger_creation(self):
        self.execute(event())
        self.assertFalse(self.path.exists())

    def test_mock_safe_send(self):
        self.assertEqual(self.execute(event(), mode="MOCK_RUNTIME").exit_code, 0)
        self.assertTrue(self.path.exists())

    def test_live_flag_required(self):
        self.assertEqual(self.execute(event(), mode="LIVE_NOTIFICATION").exit_code, 2)
        self.loader.assert_not_called(); self.transport.assert_not_called()

    def test_live_healthy_fake_transport(self):
        self.healthy()
        self.assertEqual(self.execute(event(), mode="LIVE_NOTIFICATION", live_notification_confirmed=True).exit_code, 0)
        self.transport.assert_called_once()

    def test_live_missing_blocked(self):
        result = self.execute(event(), mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.assertEqual(result.recovery_status, recovery.RECOVERABLE_NO_WRITE)
        self.assertFalse(result.runtime_invoked)
        self.assertFalse(self.path.exists())

    def test_live_manual_review_blocked(self):
        self.path.write_text("broken", encoding="utf-8")
        self.assertFalse(self.execute(event(), mode="LIVE_NOTIFICATION", live_notification_confirmed=True).runtime_invoked)

    def test_live_recovery_blocked(self):
        with mock.patch.object(recovery, "inspect_ledger", return_value=recovery.RecoveryReport()):
            self.assertFalse(self.execute(event(), mode="LIVE_NOTIFICATION", live_notification_confirmed=True).runtime_invoked)

    def test_unknown_recovery_status(self):
        with mock.patch.object(recovery, "inspect_ledger", return_value=recovery.RecoveryReport(recovery_status="fixture-secret")):
            result = self.execute(event())
        self.assertEqual(result.recovery_status, "UNKNOWN")
        self.assertNotIn("fixture-secret", repr(result.to_dict()))

    def test_recovery_exception(self):
        with mock.patch.object(recovery, "inspect_ledger", side_effect=RuntimeError("fixture-secret")):
            result = self.execute(event())
        self.assertEqual(result.exit_code, 3)
        self.assertFalse(result.runtime_invoked)
        self.assertNotIn("fixture-secret", repr(result.to_dict()))

    def test_lock_owned_then_released(self):
        observed = []
        original = recovery.inspect_ledger
        def inspect(store):
            observed.append(self.lock.exists()); return original(store)
        with mock.patch.object(recovery, "inspect_ledger", side_effect=inspect):
            result = self.execute()
        self.assertEqual(observed, [True])
        self.assertEqual(result.lock_status, "RELEASED")
        self.assertFalse(self.lock.exists())

    def test_lock_contention_no_recovery(self):
        self.lock.write_text("fixture-existing", encoding="utf-8")
        with mock.patch.object(recovery, "inspect_ledger") as inspect:
            result = self.execute(event())
            inspect.assert_not_called()
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(self.lock.read_text(), "fixture-existing")

    def test_no_stale_force_unlock(self):
        self.lock.touch(); os.utime(self.lock, (1, 1))
        self.assertEqual(self.execute().lock_status, "CONTENDED")
        self.assertTrue(self.lock.exists())

    def test_no_process_kill(self):
        self.lock.touch()
        with mock.patch.object(os, "kill") as kill:
            self.execute(); kill.assert_not_called()

    def test_root_resolved(self):
        self.assertEqual(runner.resolve_repository_root(), ROOT)

    def test_root_unknown_closed(self):
        with mock.patch.object(runner, "resolve_repository_root", side_effect=ValueError("fixture-path")):
            result = self.execute(event())
        self.assertEqual(result.repository_root_status, "UNRESOLVED")
        self.assertFalse(result.runtime_invoked)
        self.assertFalse(self.lock.exists())

    def test_changed_cwd_cli(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "scheduled_runtime_runner.py")],
                                cwd=self.temp.name, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["repository_root_status"], "RESOLVED")
        self.assertEqual(report["runner_status"], "IDLE")

    def test_secrets_and_payload_not_output(self):
        report = self.execute(event(), mode="MOCK_RUNTIME").to_dict()
        for forbidden in ("fixture-user", "fixture-app", "fixture-response", "Job completed", str(self.path)):
            self.assertNotIn(forbidden, repr(report))

    def test_env_not_opened_in_idle(self):
        with mock.patch.object(Path, "open", side_effect=AssertionError("no file reads needed")):
            self.assertEqual(self.execute().exit_code, 0)

    def test_mock_requires_fixture_dependencies(self):
        result = self.execute(event(), mode="MOCK_RUNTIME", credential_loader=None)
        self.assertIn("MOCK_DEPENDENCIES_REQUIRED", result.reason_codes)
        self.transport.assert_not_called()

    def test_mock_production_ledger_rejected(self):
        result = self.execute(event(), mode="MOCK_RUNTIME", ledger=ledger.NotificationLedger())
        self.assertFalse(result.runtime_invoked)
        self.assertNotEqual(result.exit_code, 0)

    def test_no_db_or_scheduler_power_code(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        for forbidden in ("sqlite3", "schtasks", "powercfg", "winreg", "ExecutionPolicy"):
            self.assertNotIn(forbidden, source)

    def test_critical_policy(self):
        result = self.execute(event("CRITICAL_STOP"), mode="MOCK_RUNTIME")
        self.assertEqual(result.runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.transport.assert_not_called()

    def test_no_direct_adapter_or_sender(self):
        self.assertFalse(hasattr(runner, "send_notification"))
        self.assertFalse(hasattr(runner, "adapt_notification"))

    def test_runtime_delegation_once(self):
        with mock.patch.object(runtime, "process_notification", wraps=runtime.process_notification) as invoke:
            self.execute(event(), mode="MOCK_RUNTIME")
            invoke.assert_called_once()
            self.assertIs(invoke.call_args.kwargs["ledger"], self.store)

    def test_recovery_precedes_runtime(self):
        order = []
        inspect, invoke = recovery.inspect_ledger, runtime.process_notification
        def checked(store): order.append("recovery"); return inspect(store)
        def called(*args, **kwargs): order.append("runtime"); return invoke(*args, **kwargs)
        with mock.patch.object(recovery, "inspect_ledger", side_effect=checked), mock.patch.object(runtime, "process_notification", side_effect=called):
            self.execute(event())
        self.assertEqual(order[:2], ["recovery", "runtime"])

    def test_no_loop_or_daemon(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertNotIn("while ", source)
        self.assertNotIn("sleep(", source)

    def test_exit_success(self):
        self.assertEqual(self.execute().exit_code, 0)

    def test_idle_normal(self):
        result = self.execute()
        self.assertEqual(result.runner_status, "IDLE")
        self.assertFalse(result.runtime_invoked)

    def test_runtime_exception_safe(self):
        with mock.patch.object(runtime, "process_notification", side_effect=RuntimeError("fixture-secret")):
            result = self.execute(event())
        self.assertEqual(result.exit_code, 3)
        self.assertTrue(result.runtime_invoked)
        self.assertIsNone(result.notification_attempted)
        self.assertNotIn("fixture-secret", repr(result.to_dict()))

    def test_runtime_malformed_result(self):
        with mock.patch.object(runtime, "process_notification", return_value={"secret": "fixture"}):
            result = self.execute(event())
        self.assertEqual(result.exit_code, 3)

    def test_cli_live_disabled_even_with_flag(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO), mock.patch.object(runner, "run_once") as run:
            self.assertEqual(runner.main(["--mode", "LIVE_NOTIFICATION", "--confirm-live"]), 2)
            run.assert_not_called()

    def test_cli_unknown_no_echo(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(runner.main(["fixture-private"]), 2)
            self.assertNotIn("fixture-private", output.getvalue())

    def test_unknown_mode(self):
        self.assertEqual(self.execute(mode="OTHER").exit_code, 2)

    def test_unknown_version(self):
        self.assertEqual(self.execute(runner_version="9").exit_code, 2)

    def test_bad_live_flag(self):
        self.assertEqual(self.execute(live_notification_confirmed=1).exit_code, 2)

    def test_lock_outside_temp_rejected(self):
        self.assertEqual(self.execute(lock_path=ROOT / "forbidden.lock").exit_code, 3)

    def test_lock_release_failure_safe(self):
        with mock.patch.object(Path, "unlink", side_effect=PermissionError()):
            result = self.execute()
        self.assertEqual(result.lock_status, "RELEASE_FAILED")
        self.assertEqual(result.exit_code, 3)
        self.assertTrue(self.lock.exists())

    def test_lock_contention_concurrent(self):
        entered, release = threading.Event(), threading.Event()
        results = []
        def slow(*args):
            entered.set()
            if not release.wait(5): raise TimeoutError()
            return {"status": 1}
        thread = threading.Thread(target=lambda: results.append(self.execute(event(), mode="MOCK_RUNTIME", transport=slow)))
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.execute().lock_status, "CONTENDED")
        finally:
            release.set(); thread.join(5)
        self.assertEqual(results[0].exit_code, 0)

    def test_queue_input_nonmutation(self):
        value = event(); before = deepcopy(value)
        self.execute(value)
        self.assertEqual(value, before)

    def test_safe_output_exact_fields(self):
        expected = {"runner_version", "mode", "runner_status", "recovery_status",
                    "execution_started_at_utc", "execution_finished_at_utc", "runtime_invoked",
                    "runtime_status", "notification_attempted", "lock_status", "repository_root_status",
                    "exit_code", "reason_codes"}
        self.assertEqual(set(self.execute().to_dict()), expected)

    def test_runner_runtime_reason_allowlist_is_fixed(self):
        self.assertEqual(runner.SAFE_RUNTIME_REPORT_REASONS,
                         frozenset({"INCIDENT_REMINDER_SELECTED"}))

    def test_env_cannot_promote_mode(self):
        with mock.patch.dict(os.environ, {"RUNNER_MODE": "LIVE_NOTIFICATION"}):
            self.assertEqual(self.execute().mode, "DRY_RUN")

    def test_timestamp_order(self):
        result = self.execute()
        self.assertLessEqual(result.execution_started_at_utc, result.execution_finished_at_utc)


if __name__ == "__main__":
    unittest.main()
