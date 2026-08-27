from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import notification_ledger as ledger
import unattended_runtime as runtime


def event(kind="JOB_COMPLETED"):
    return {"event_version": "0.1", "event_type": kind, "job_id": "ledger-fixture",
            "job_type": "static_validation", "severity": "CRITICAL" if kind == "CRITICAL_STOP" else "INFO",
            "state": {"JOB_COMPLETED": "DONE", "JOB_STARTED": "RUNNING", "CRITICAL_STOP": "FAILED_SAFE"}[kind],
            "approval_required": False, "summary_code": "SAFE_EVENT",
            "occurred_at": "2026-08-27T00:00:00+09:00"}


class NotificationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.json"
        self.store = ledger.NotificationLedger(self.path)
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-response"})
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))

    def execute(self, value=None, **kwargs):
        options = dict(mode="MOCK_RUNTIME", ledger=self.store,
                       credential_loader=self.loader, transport=self.transport)
        options.update(kwargs)
        return runtime.process_notification(event() if value is None else value, **options)

    def records(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def corrupt(self, text):
        self.path.write_text(text, encoding="utf-8")

    def test_new_identity(self):
        with self.store.transaction() as tx:
            self.assertEqual(tx.lookup(runtime.event_identity(event())), "NEW")
        self.assertFalse(self.path.exists())

    def test_success_saved(self):
        result = self.execute()
        self.assertEqual(result.runtime_status, "NOTIFICATION_DELIVERED")
        self.assertEqual(self.records()[0]["event_identity"], runtime.event_identity(event()))

    def test_fresh_runtime_suppresses(self):
        self.execute()
        self.transport.reset_mock()
        result = self.execute(ledger=ledger.NotificationLedger(self.path))
        self.assertEqual(result.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.assertFalse(result.delivery_attempted)
        self.transport.assert_not_called()

    def test_failure_not_saved(self):
        self.transport.return_value = {"status": 0}
        self.assertEqual(self.execute().runtime_status, "NOTIFICATION_FAILED_SAFE")
        self.assertFalse(self.path.exists())

    def test_timeout_not_saved(self):
        self.transport.side_effect = TimeoutError("fixture-secret")
        self.assertFalse(self.execute().delivery_succeeded)
        self.assertFalse(self.path.exists())

    def test_exception_not_saved(self):
        result = self.execute(sender_fn=mock.Mock(side_effect=RuntimeError("fixture-secret")))
        self.assertEqual(result.runtime_status, "NOTIFICATION_FAILED_SAFE")
        self.assertFalse(self.path.exists())
        self.assertNotIn("fixture-secret", repr(result.to_dict()))

    def test_failure_then_retry_new_process_session(self):
        self.transport.return_value = {"status": 0}
        self.execute()
        self.transport.return_value = {"status": 1}
        self.assertTrue(self.execute(ledger=ledger.NotificationLedger(self.path)).delivery_succeeded)

    def test_dry_run_missing_no_creation(self):
        result = self.execute(mode="DRY_RUN")
        self.assertEqual(result.runtime_status, "NOTIFICATION_READY")
        self.assertEqual(list(self.path.parent.iterdir()), [])
        self.transport.assert_not_called()

    def test_dry_run_existing_unchanged(self):
        self.execute()
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.execute(mode="DRY_RUN")
        self.assertEqual(before, (self.path.read_bytes(), self.path.stat().st_mtime_ns))

    def test_mock_rejects_production_store(self):
        result = self.execute(ledger=ledger.NotificationLedger())
        self.assertIn("LEDGER_TEST_PATH_REQUIRED", result.reason_codes)
        self.loader.assert_not_called()
        self.transport.assert_not_called()

    def test_mock_rejects_non_temp_path(self):
        result = self.execute(ledger=ledger.NotificationLedger(ROOT / "runtime" / "test.json"))
        self.assertIn("LEDGER_TEST_PATH_REQUIRED", result.reason_codes)
        self.transport.assert_not_called()

    def test_mock_default_is_isolated(self):
        with mock.patch.object(ledger.NotificationLedger, "_replace", autospec=True) as replace:
            self.execute(ledger=None)
            self.assertTrue(replace.call_args.args[0].test_only)
            self.assertNotEqual(replace.call_args.args[0].path, ledger.DEFAULT_PATH)

    def test_corrupt_live_fails_before_credentials(self):
        self.corrupt("broken")
        result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.assertIn("LEDGER_CORRUPT", result.reason_codes)
        self.transport.assert_not_called()
        self.loader.assert_not_called()
        self.assertEqual(self.path.read_text(), "broken")

    def test_partial_final_write_rejected(self):
        self.corrupt('[{"ledger_version":"0.1"')
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_missing_final_newline_rejected(self):
        self.corrupt("[]")
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_malformed_record(self):
        self.corrupt('[{"extra":"fixture"}]\n')
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_unknown_record_version(self):
        self.execute()
        rows = self.records(); rows[0]["ledger_version"] = "9"
        self.corrupt(json.dumps(rows) + "\n")
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_unsuccessful_record_rejected(self):
        self.execute()
        rows = self.records(); rows[0]["delivery_status"] = "SEND_FAILED_SAFE"
        self.corrupt(json.dumps(rows) + "\n")
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_duplicate_json_key(self):
        self.corrupt('[{"ledger_version":"0.1","ledger_version":"0.1"}]\n')
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_duplicate_record(self):
        self.execute(); rows = self.records()
        self.corrupt(json.dumps(rows + rows) + "\n")
        self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_secret_and_raw_data_absent(self):
        self.execute(); text = self.path.read_text()
        for forbidden in ("fixture-user", "fixture-app", "fixture-response", "payload", "token", "message", "title", "request", "credential"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(set(self.records()[0]), ledger.RECORD_FIELDS)

    def test_critical_unchanged(self):
        result = self.execute(event("CRITICAL_STOP"))
        self.assertTrue(result.emergency_blocked)
        self.assertEqual(result.runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.assertFalse(self.path.exists())
        self.transport.assert_not_called()

    def test_suppressed_does_not_touch_ledger(self):
        with mock.patch.object(self.store, "transaction", side_effect=AssertionError("must not open")):
            result = self.execute(event("JOB_STARTED"))
        self.assertTrue(result.notification_suppressed)
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_subprocess_restart_dedupe(self):
        self.execute()
        script = (
            "import sys,json;sys.path.insert(0,sys.argv[1]);"
            "import unattended_runtime as r;from notification_ledger import NotificationLedger;"
            "f=lambda *a,**k: (_ for _ in ()).throw(AssertionError('not called'));"
            "out=r.process_notification(json.loads(sys.argv[3]),mode='MOCK_RUNTIME',"
            "ledger=NotificationLedger(sys.argv[2]),credential_loader=f,transport=f);"
            "print(out.runtime_status)"
        )
        result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT / "scripts"), str(self.path), json.dumps(event())],
                                capture_output=True, text=True, timeout=15, check=True)
        self.assertEqual(result.stdout.strip(), "NOTIFICATION_DUPLICATE_SUPPRESSED")

    def test_concurrent_duplicate_lock(self):
        entered, release = threading.Event(), threading.Event()
        outcomes = []
        def slow_transport(*args):
            entered.set()
            if not release.wait(5): raise TimeoutError()
            return {"status": 1}
        thread = threading.Thread(target=lambda: outcomes.append(self.execute(transport=slow_transport)))
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            second = self.execute(ledger=ledger.NotificationLedger(self.path))
            self.assertIn("LEDGER_BUSY", second.reason_codes)
            self.transport.assert_not_called()
        finally:
            release.set(); thread.join(5)
        self.assertTrue(outcomes[0].delivery_succeeded)
        self.assertEqual(self.execute().runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")

    def test_stale_lock_fail_closed(self):
        self.path.with_name(self.path.name + ".lock").touch()
        self.assertIn("LEDGER_BUSY", self.execute().reason_codes)
        self.transport.assert_not_called()

    def test_write_failure_retains_delivery_fact(self):
        with mock.patch.object(ledger.os, "replace", side_effect=OSError("fixture-secret")):
            result = self.execute()
        self.assertEqual(result.runtime_status, "NOTIFICATION_FAILED_SAFE")
        self.assertTrue(result.delivery_attempted)
        self.assertTrue(result.delivery_succeeded)
        self.assertIn("LEDGER_WRITE_FAILED", result.reason_codes)
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_failed_replace_keeps_previous_records(self):
        self.execute(); before = self.path.read_bytes()
        different = event(); different["job_id"] = "other-job"
        with mock.patch.object(ledger.os, "replace", side_effect=OSError()):
            self.execute(different)
        self.assertEqual(self.path.read_bytes(), before)

    def test_dry_transaction_cannot_write(self):
        with self.store.transaction() as tx:
            with self.assertRaises(ledger.LedgerError):
                tx.record_success(runtime.event_identity(event()), "JOB_COMPLETED")

    def test_sender_malformed_success_not_recorded(self):
        import pushover_sender
        bad = pushover_sender.SenderResult("0.1", "MOCK_SEND", "SEND_FAILED_SAFE", True, True, False, False, True, ())
        result = self.execute(sender_fn=lambda *a, **k: bad)
        self.assertEqual(result.runtime_status, "NOTIFICATION_FAILED_SAFE")
        self.assertFalse(self.path.exists())

    def test_queue_input_unchanged(self):
        value = event(); before = deepcopy(value)
        self.execute(value)
        self.assertEqual(value, before)

    def test_duplicate_no_adapter_or_sender(self):
        self.execute(); adapter = mock.Mock(); sender = mock.Mock()
        self.execute(adapter_fn=adapter, sender_fn=sender)
        adapter.assert_not_called(); sender.assert_not_called()

    def test_safe_result_allowlist(self):
        self.execute()
        self.assertEqual(set(self.execute().to_dict()), runtime.OUTPUT_FIELDS)

    def test_record_timestamp_utc(self):
        self.execute()
        stamp = self.records()[0]["recorded_at_utc"]
        self.assertTrue(stamp.endswith("Z"))
        self.assertLessEqual(datetime.fromisoformat(stamp.replace("Z", "+00:00")), datetime.now(timezone.utc))

    def test_oversized_file_rejected(self):
        with mock.patch.object(ledger, "MAX_BYTES", 4):
            self.corrupt("[    ]\n")
            self.assertIn("LEDGER_CORRUPT", self.execute().reason_codes)

    def test_live_test_store_requires_fake_transport(self):
        result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True, transport=None)
        self.assertIn("LEDGER_TEST_TRANSPORT_REQUIRED", result.reason_codes)
        self.loader.assert_not_called()

    def test_mock_no_real_ledger_access(self):
        with mock.patch.object(ledger.NotificationLedger, "_read", autospec=True, return_value=[]) as read:
            self.execute(ledger=None)
            self.assertTrue(read.call_args.args[0].test_only)


if __name__ == "__main__":
    unittest.main()
