from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from tests.test_unattended_runtime import event
from tests.test_unattended_job_queue import queue
import unattended_runtime as runtime
import pushover_notification_adapter as adapter
import pushover_sender as sender
import notification_ledger as ledger
import ledger_recovery as recovery
import scheduled_runtime_live_canary as canary


CANARY_ID = "d3ef3e57785d35ade98cff12e6566695b939c1938b73b6b340d726c934b34fa4"


def queue_event():
    return dict(event_version="0.2", event_type="QUEUE_BLOCKED", subject_type="QUEUE",
        queue_id=queue.get_queue_identity().queue_id, occurred_at="2026-08-27T00:00:00Z",
        severity="ERROR", state="QUEUE_BLOCKED", approval_required=False, summary_code="QUEUE_BLOCKED")


def job_event(kind="JOB_COMPLETED"):
    return dict(event(kind), event_version="0.2", subject_type="JOB")


class SafeNotificationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="schema-v02-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.json"
        self.path.write_text("[]\n", encoding="utf-8")
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1, "request": "fixture-raw-response"})
        for name in ("_default_transport", "load_credentials"):
            patcher = mock.patch.object(sender, name, side_effect=AssertionError("REAL_IO_FORBIDDEN"))
            self.addCleanup(patcher.stop)
            patched = patcher.start()
            self.addCleanup(patched.assert_not_called)

    def run_event(self, source, mode="DRY_RUN"):
        return runtime.process_notification(source, mode=mode, ledger=self.store,
            credential_loader=self.loader, transport=self.transport)

    def test_exact_schemas(self):
        self.assertEqual(len(runtime.EVENT_FIELDS), 9)
        self.assertEqual(len(queue.V02_JOB_FIELDS), 10)
        self.assertEqual(len(queue.V02_QUEUE_FIELDS), 9)
        self.assertEqual(set(queue_event()), queue.V02_QUEUE_FIELDS)
        self.assertEqual(set(job_event()), queue.V02_JOB_FIELDS)

    def test_queue_typed(self):
        source = queue.create_event(**queue_event())
        self.assertIsInstance(source, queue.QueueNotificationEventV02)
        self.assertNotIn("job_id", source.to_dict())
        self.assertNotIn("job_type", source.to_dict())
        self.assertEqual(self.run_event(source).runtime_status, "NOTIFICATION_READY")
        self.assertEqual(runtime.event_identity(source), runtime.event_identity(source.to_dict()))

    def test_job_typed(self):
        source = queue.create_event(**job_event())
        self.assertIsInstance(source, queue.JobNotificationEventV02)
        self.assertEqual(self.run_event(source).runtime_status, "NOTIFICATION_READY")

    def test_canary_identity_unchanged(self):
        self.assertEqual(runtime.event_identity(canary.canary_event()), CANARY_ID)
        self.assertIsNotNone(queue.create_event(**canary.canary_event()))
        self.assertEqual(adapter.adapt_notification(canary.canary_event()).notification_status, "READY")

    @unittest.skipUnless(ledger.DEFAULT_PATH.is_file(),
                         "production notification ledger is not present")
    def test_production_record_read_compatibility(self):
        # Read-only: no bootstrap, transaction writes, transport or LIVE invocation.
        before = ledger.DEFAULT_PATH.read_bytes()
        state = recovery.inspect_ledger(ledger.NotificationLedger())
        self.assertEqual(state.recovery_status, "HEALTHY")
        self.assertEqual(state.record_count, 1)
        self.assertIn(CANARY_ID, before.decode("utf-8"))
        result = runtime.process_notification(canary.canary_event(), mode="DRY_RUN")
        self.assertEqual(result.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.assertEqual(before, ledger.DEFAULT_PATH.read_bytes())

    def test_identity_deterministic(self):
        source = queue_event()
        self.assertEqual(runtime.event_identity(source), runtime.event_identity(dict(reversed(list(source.items())))))

    def test_identity_includes_queue_id_but_does_not_authorize_it(self):
        source = queue_event()
        other = dict(source, queue_id="unapproved-queue")
        self.assertNotEqual(runtime.event_identity(source), runtime.event_identity(other))
        self.assertIsNone(queue.create_event(**other))
        self.assertEqual(self.run_event(other).runtime_status, "INVALID_INPUT")

    def test_cross_subject_identity(self):
        self.assertEqual(len({runtime.event_identity(queue_event()), runtime.event_identity(job_event()),
                             runtime.event_identity(event("JOB_COMPLETED"))}), 3)

    def test_event_type_identity(self):
        self.assertNotEqual(runtime.event_identity(job_event("JOB_FAILED_SAFE")), runtime.event_identity(job_event()))

    def test_timestamp_identity(self):
        self.assertNotEqual(runtime.event_identity(queue_event()),
                            runtime.event_identity(dict(queue_event(), occurred_at="2026-08-28T00:00:00Z")))

    def test_existing_hash_function_reused(self):
        with mock.patch.object(runtime.hashlib, "sha256", wraps=runtime.hashlib.sha256) as hash_fn:
            runtime.event_identity(queue_event())
            hash_fn.assert_called_once()

    def test_queue_validator_reused(self):
        with mock.patch.object(queue, "validate_queue_identity", return_value=False) as validate:
            self.assertIsNone(queue.create_event(**queue_event()))
            validate.assert_called_once()

    def test_runtime_and_adapter_delegate(self):
        with mock.patch.object(queue, "create_event", return_value=None) as create:
            self.assertEqual(self.run_event(queue_event()).runtime_status, "INVALID_INPUT")
            self.assertEqual(adapter.adapt_notification(queue_event()).notification_status, "INVALID_INPUT")
            self.assertEqual(create.call_count, 2)

    def test_adapter_policy_unchanged(self):
        actual = adapter.adapt_notification(queue_event())
        old = adapter.adapt_notification(event("QUEUE_BLOCKED"))
        self.assertEqual(actual.to_dict(), old.to_dict())
        self.assertEqual((actual.pushover_priority, actual.delivery_class), (1, "IMMEDIATE"))
        self.assertNotIn(queue.MAIN_QUEUE_ID, actual.message)
        self.assertFalse(actual.approval_required)

    def test_dry_read_only(self):
        before = self.path.read_bytes()
        result = self.run_event(queue_event())
        self.assertEqual(result.runtime_status, "NOTIFICATION_READY")
        self.assertFalse(result.delivery_attempted)
        self.assertEqual(before, self.path.read_bytes())
        # Existing Sender DRY_RUN checks credential presence via the fixture.
        self.loader.assert_called_once()
        self.transport.assert_not_called()

    def test_mock_and_duplicate(self):
        source = queue_event()
        first = self.run_event(source, "MOCK_RUNTIME")
        self.assertEqual(first.runtime_status, "NOTIFICATION_DELIVERED")
        self.assertTrue(first.delivery_succeeded)
        self.transport.assert_called_once()
        self.assertEqual(recovery.inspect_ledger(self.store).record_count, 1)
        before = self.path.read_bytes()
        with mock.patch.object(runtime.pushover_sender, "_send", side_effect=AssertionError()):
            second = self.run_event(source, "MOCK_RUNTIME")
        self.assertEqual(second.runtime_status, "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.assertFalse(second.delivery_attempted)
        self.assertEqual(before, self.path.read_bytes())
        self.transport.assert_called_once()
        self.assertNotIn(b"queue_id", before)
        self.assertNotIn(queue.MAIN_QUEUE_ID.encode(), before)

    def test_safe_output(self):
        result = self.run_event(queue_event(), "MOCK_RUNTIME")
        output = json.dumps(result.to_dict())
        self.assertEqual(set(result.to_dict()), runtime.OUTPUT_FIELDS)
        for value in ("fixture-user", "fixture-app", "fixture-raw-response", "queue_id", "payload", "traceback"):
            self.assertNotIn(value, output)

    def test_failure_isolation(self):
        source = queue_event()
        before = dict(source)
        self.transport.side_effect = TimeoutError("fixture-private")
        result = self.run_event(source, "MOCK_RUNTIME")
        self.assertFalse(result.delivery_succeeded)
        self.assertEqual(source, before)
        self.assertNotIn("fixture-private", repr(result))

    def test_critical_legacy_block(self):
        self.assertEqual(self.run_event(event("CRITICAL_STOP"), "MOCK_RUNTIME").runtime_status, "EMERGENCY_SEND_BLOCKED")
        self.transport.assert_not_called()


def compatible(kind, version):
    def test(self):
        source = event(kind) if version == "0.1" else job_event(kind)
        self.assertIsNotNone(queue.create_event(**source))
        result = self.run_event(source)
        self.assertIn(result.runtime_status, {"NOTIFICATION_READY", "NOTIFICATION_SUPPRESSED"})
    return test


for _kind in ("JOB_WAITING_APPROVAL", "JOB_FAILED_SAFE", "JOB_COMPLETED", "JOB_STARTED", "JOB_CHECKPOINTED", "JOB_SWITCHED"):
    for _version in ("0.1", "0.2"):
        setattr(SafeNotificationSchemaTests, "test_compat_" + _kind + _version.replace(".", ""), compatible(_kind, _version))


def invalid(subject, updates, remove=()):
    def test(self):
        value = dict(queue_event() if subject == "QUEUE" else job_event(), **updates)
        for field in remove:
            value.pop(field)
        self.assertIsNone(queue.create_event(**value))
        self.assertEqual(adapter.adapt_notification(value).notification_status, "INVALID_INPUT")
        self.assertEqual(self.run_event(value).runtime_status, "INVALID_INPUT")
        self.transport.assert_not_called()
    return test


for _name, _subject, _updates, _remove in [
    ("missing_queue", "QUEUE", {}, ("queue_id",)),
    ("bad_queue", "QUEUE", {"queue_id": "../bad"}, ()),
    ("unknown_queue", "QUEUE", {"queue_id": "unapproved"}, ()),
    ("queue_job_mix", "QUEUE", {"job_id": "fake", "job_type": "fake"}, ()),
    ("queue_job_event", "QUEUE", {"event_type": "JOB_COMPLETED"}, ()),
    ("queue_idle", "QUEUE", {"event_type": "QUEUE_IDLE"}, ()),
    ("queue_critical", "QUEUE", {"event_type": "CRITICAL_STOP"}, ()),
    ("queue_job_state", "QUEUE", {"state": "BLOCKED"}, ()),
    ("queue_approval", "QUEUE", {"approval_required": True}, ()),
    ("queue_summary", "QUEUE", {"summary_code": "ARBITRARY"}, ()),
    ("queue_unknown", "QUEUE", {"extra": "value"}, ()),
    ("version", "QUEUE", {"event_version": "9"}, ()),
    ("subject", "QUEUE", {"subject_type": "OTHER"}, ()),
    ("subject_type", "QUEUE", {"subject_type": []}, ()),
    ("timestamp", "QUEUE", {"occurred_at": "invalid"}, ()),
    ("naive", "QUEUE", {"occurred_at": "2026-08-27T00:00:00"}, ()),
    ("missing_job_id", "JOB", {}, ("job_id",)),
    ("missing_job_type", "JOB", {}, ("job_type",)),
    ("bad_job", "JOB", {"job_id": "secret-token"}, ()),
    ("job_queue_mix", "JOB", {"queue_id": queue.MAIN_QUEUE_ID}, ()),
    ("job_queue_alias", "JOB", {"job_id": queue.MAIN_QUEUE_ID}, ()),
    ("job_blocked", "JOB", {"event_type": "QUEUE_BLOCKED"}, ()),
    ("job_critical", "JOB", {"event_type": "CRITICAL_STOP"}, ()),
    ("job_bad_state", "JOB", {"state": "READY"}, ()),
    ("job_extra", "JOB", {"extra": "value"}, ()),
]:
    setattr(SafeNotificationSchemaTests, "test_invalid_" + _name, invalid(_subject, _updates, _remove))


if __name__ == "__main__":
    unittest.main()
