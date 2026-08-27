from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ledger_recovery as recovery
import notification_ledger as ledger
import unattended_runtime as runtime
from tests.test_notification_ledger import event


class LedgerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recovery-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.json"
        self.store = ledger.NotificationLedger(self.path)
        self.lock = self.path.with_name(self.path.name + ".lock")
        self.artifact = self.path.with_name(self.path.name + ".fixture.tmp")
        self.transport = mock.Mock(return_value={"status": 1})
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))

    def record(self):
        return {"ledger_version": "0.1", "event_identity": runtime.event_identity(event()),
                "event_type": "JOB_COMPLETED", "delivery_status": "NOTIFICATION_DELIVERED",
                "recorded_at_utc": "2026-08-27T00:00:00Z"}

    def write(self, rows):
        self.path.write_text(json.dumps(rows) + "\n", encoding="utf-8")

    def check(self):
        return recovery.inspect_ledger(self.store)

    def execute(self, **kwargs):
        options = dict(mode="MOCK_RUNTIME", ledger=self.store, credential_loader=self.loader,
                       transport=self.transport)
        options.update(kwargs)
        return runtime.process_notification(event(), **options)

    def test_healthy(self):
        self.write([self.record()]); result = self.check()
        self.assertEqual(result.recovery_status, recovery.HEALTHY)
        self.assertEqual(result.record_count, 1)

    def test_healthy_empty(self):
        self.write([]); self.assertEqual(self.check().recovery_status, recovery.HEALTHY)

    def test_missing(self):
        result = self.check()
        self.assertEqual(result.recovery_status, recovery.RECOVERABLE_NO_WRITE)
        self.assertIsNone(result.record_count)
        self.assertFalse(self.path.exists())

    def test_malformed_json(self):
        self.path.write_text("{bad", encoding="utf-8")
        self.assertEqual(self.check().recovery_status, recovery.MANUAL_REVIEW_REQUIRED)

    def test_version(self):
        row = self.record(); row["ledger_version"] = "private-fixture-version"
        self.write([row]); report = self.check()
        self.assertEqual(report.ledger_version_detected, "UNSUPPORTED")
        self.assertNotIn("private-fixture", repr(report.to_dict()))

    def test_missing_field(self):
        row = self.record(); del row["event_type"]; self.write([row])
        self.assertTrue(self.check().corruption_detected)

    def test_invalid_identity(self):
        row = self.record(); row["event_identity"] = "bad"; self.write([row])
        self.assertTrue(self.check().corruption_detected)

    def test_conflicting_identity(self):
        row = self.record(); other = dict(row, event_type="QUEUE_BLOCKED")
        self.write([row, other]); report = self.check()
        self.assertEqual(report.duplicate_identity_count, 1)
        self.assertEqual(report.recovery_status, recovery.MANUAL_REVIEW_REQUIRED)

    def test_identical_duplicate_record(self):
        row = self.record(); self.write([row, row])
        self.assertTrue(self.check().corruption_detected)

    def test_duplicate_json_key(self):
        self.path.write_text('[{"ledger_version":"0.1","ledger_version":"0.1"}]\n', encoding="utf-8")
        self.assertTrue(self.check().corruption_detected)

    def test_active_transaction_blocks(self):
        self.write([])
        with self.store.transaction(writable=True):
            report = self.check()
            self.assertEqual(report.lock_status, "UNKNOWN")
            result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
            self.assertFalse(result.delivery_attempted)
        self.transport.assert_not_called()

    def test_unknown_lock_preserved(self):
        self.lock.write_text("fixture-private-owner", encoding="utf-8")
        self.assertEqual(self.check().lock_status, "UNKNOWN")
        self.assertEqual(self.lock.read_text(), "fixture-private-owner")

    def test_stale_candidate_not_unlocked(self):
        self.lock.touch(); old = time.time() - 7200; os.utime(self.lock, (old, old))
        self.assertEqual(self.check().lock_status, "STALE_CANDIDATE")
        self.assertTrue(self.lock.exists())

    def test_valid_temp_never_promoted(self):
        self.artifact.write_text("[]\n", encoding="utf-8")
        result = self.check()
        self.assertEqual(result.temp_artifact_status, "VALID_CANDIDATE")
        self.assertEqual(result.recovery_status, recovery.MANUAL_REVIEW_REQUIRED)
        self.assertFalse(self.path.exists())
        self.assertTrue(self.artifact.exists())

    def test_malformed_temp(self):
        self.artifact.write_text("partial", encoding="utf-8")
        self.assertEqual(self.check().temp_artifact_status, "MALFORMED_CANDIDATE")

    def test_unknown_temp(self):
        self.artifact.mkdir()
        self.assertEqual(self.check().temp_artifact_status, "UNKNOWN")

    def test_mixed_temp(self):
        self.artifact.write_text("[]\n", encoding="utf-8")
        self.path.with_name(self.path.name + ".other.tmp").write_text("bad", encoding="utf-8")
        self.assertEqual(self.check().temp_artifact_status, "MIXED_CANDIDATES")

    def test_files_bytes_and_mtime_unchanged(self):
        self.write([self.record()]); self.lock.touch(); self.artifact.write_text("bad", encoding="utf-8")
        paths = (self.path, self.lock, self.artifact)
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
        self.check()
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])

    def test_no_delete_or_rename(self):
        self.write([])
        with mock.patch.object(Path, "unlink", side_effect=AssertionError()), \
             mock.patch.object(os, "replace", side_effect=AssertionError()):
            self.assertEqual(self.check().recovery_status, recovery.HEALTHY)

    def test_no_process_kill(self):
        self.lock.touch()
        with mock.patch.object(os, "kill", side_effect=AssertionError()) as kill:
            self.check()
            kill.assert_not_called()

    def test_safe_report_exact_fields(self):
        expected = {"recovery_version", "recovery_status", "ledger_version_detected", "ledger_path_class",
                    "corruption_detected", "lock_status", "temp_artifact_detected", "temp_artifact_status",
                    "record_count", "duplicate_identity_count", "action_required", "checked_at_utc", "reason_codes"}
        self.assertEqual(set(self.check().to_dict()), expected)

    def test_secret_payload_response_absent(self):
        self.write([dict(self.record(), credential="fixture-secret", payload="fixture-payload", response="fixture-response")])
        text = repr(self.check().to_dict())
        for forbidden in ("fixture-secret", "fixture-payload", "fixture-response", str(self.path)):
            self.assertNotIn(forbidden, text)

    def test_live_missing_blocked(self):
        result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.assertIn("LEDGER_MISSING", result.reason_codes)
        self.loader.assert_not_called(); self.transport.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_live_healthy_fake_transport(self):
        self.write([])
        result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.assertTrue(result.delivery_succeeded)

    def test_live_corruption_blocked_before_sender(self):
        self.path.write_text("bad", encoding="utf-8")
        result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.assertFalse(result.delivery_attempted)
        self.loader.assert_not_called(); self.transport.assert_not_called()

    def test_dry_run_diagnostic(self):
        self.path.write_text("bad", encoding="utf-8")
        self.assertIn("LEDGER_CORRUPT", self.execute(mode="DRY_RUN").reason_codes)
        self.loader.assert_not_called()

    def test_mock_production_store_rejected(self):
        with mock.patch.object(recovery, "_snapshot", side_effect=AssertionError()) as read:
            self.assertIn("LEDGER_TEST_PATH_REQUIRED", self.execute(ledger=ledger.NotificationLedger()).reason_codes)
            read.assert_not_called()

    def test_critical_still_blocked(self):
        self.write([])
        result = runtime.process_notification(event("CRITICAL_STOP"), mode="MOCK_RUNTIME", ledger=self.store,
                                              credential_loader=self.loader, transport=self.transport)
        self.assertTrue(result.emergency_blocked)
        self.transport.assert_not_called()

    def test_queue_event_unchanged(self):
        self.lock.touch(); value = event(); before = deepcopy(value)
        runtime.process_notification(value, mode="MOCK_RUNTIME", ledger=self.store,
                                     credential_loader=self.loader, transport=self.transport)
        self.assertEqual(value, before)

    def test_adapter_sender_not_called_on_preflight_failure(self):
        self.artifact.write_text("[]\n", encoding="utf-8")
        adapter, sender = mock.Mock(), mock.Mock()
        self.execute(adapter_fn=adapter, sender_fn=sender)
        adapter.assert_not_called(); sender.assert_not_called()

    def test_read_permission_failure(self):
        with mock.patch.object(recovery, "_snapshot", side_effect=PermissionError("private-fixture")):
            report = self.check()
        self.assertEqual(report.recovery_status, recovery.RECOVERY_BLOCKED)
        self.assertNotIn("private-fixture", repr(report.to_dict()))

    def test_path_rejected(self):
        report = recovery.inspect_ledger(ledger.NotificationLedger(ROOT / "forbidden.json"))
        self.assertEqual(report.ledger_path_class, "REJECTED")
        self.assertEqual(report.recovery_status, recovery.MANUAL_REVIEW_REQUIRED)

    def test_symlink_path_rejected(self):
        with mock.patch.object(self.store, "_check_path", side_effect=ledger.LedgerError("LEDGER_PATH_INVALID")):
            self.assertEqual(self.check().ledger_path_class, "REJECTED")

    def test_internal_exception_safe(self):
        with mock.patch.object(recovery, "_temps", side_effect=RuntimeError("fixture-secret")):
            report = self.check()
        self.assertEqual(report.recovery_status, recovery.RECOVERY_BLOCKED)
        self.assertNotIn("fixture-secret", repr(report.to_dict()))

    def test_unknown_recovery_version(self):
        self.assertEqual(recovery.inspect_ledger(self.store, recovery_version="9").recovery_status, recovery.RECOVERY_BLOCKED)

    def test_cli_read_only(self):
        self.write([]); before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "ledger_recovery.py"),
                                 "--check", "--test-ledger", str(self.path)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["recovery_status"], recovery.HEALTHY)
        self.assertNotIn(str(self.path), result.stdout)
        self.assertEqual(before, (self.path.read_bytes(), self.path.stat().st_mtime_ns))

    def test_cli_bad_args_no_echo(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "ledger_recovery.py"),
                                 "--private-fixture"], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-fixture", result.stdout + result.stderr)

    def test_recovery_then_dedupe(self):
        self.execute(); self.assertEqual(self.check().recovery_status, recovery.HEALTHY)
        self.transport.reset_mock()
        self.assertEqual(self.execute().runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.transport.assert_not_called()

    def test_unknown_runtime_preflight_status_blocked(self):
        with mock.patch.object(runtime, "inspect_ledger", return_value=recovery.RecoveryReport(recovery_status="OTHER")):
            result = self.execute(mode="LIVE_NOTIFICATION", live_notification_confirmed=True)
        self.assertFalse(result.delivery_attempted)

    def test_invalid_timestamp(self):
        row = self.record(); row["recorded_at_utc"] = "not-a-time"; self.write([row])
        self.assertTrue(self.check().corruption_detected)


if __name__ == "__main__":
    unittest.main()
