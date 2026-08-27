from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pushover_notification_adapter as adapter  # noqa: E402


NOW = "2026-08-27T00:00:00+09:00"


def event(event_type="JOB_COMPLETED", **changes):
    values = {
        "event_version": "0.1", "event_type": event_type, "job_id": "job-a",
        "job_type": "static_validation", "severity": "INFO", "state": "DONE",
        "approval_required": False, "summary_code": "JOB_COMPLETED_SAFE",
        "occurred_at": NOW,
    }
    if event_type == "JOB_WAITING_APPROVAL":
        values.update(severity="WARN", state="WAITING_APPROVAL", approval_required=True, summary_code="APPROVAL_REQUIRED")
    elif event_type == "CRITICAL_STOP":
        values.update(severity="CRITICAL", state="FAILED_SAFE", summary_code="QUEUE_FAIL_CLOSED")
    values.update(changes)
    return values


class PushoverNotificationAdapterTests(unittest.TestCase):
    def adapt(self, event_type="JOB_COMPLETED", **changes):
        return adapter.adapt_notification(event(event_type, **changes))

    def test_01_adapter_version(self): self.assertEqual(adapter.ADAPTER_VERSION, "0.1")
    def test_02_started_mapping(self): self.assertEqual(self.adapt("JOB_STARTED", state="RUNNING").pushover_priority, -1)
    def test_03_completed_mapping(self): self.assertEqual(self.adapt().pushover_priority, 0)
    def test_04_failed_mapping(self): self.assertEqual(self.adapt("JOB_FAILED_SAFE", severity="ERROR", state="FAILED_SAFE").pushover_priority, 1)
    def test_05_approval_mapping(self): self.assertEqual(self.adapt("JOB_WAITING_APPROVAL").pushover_priority, 1)
    def test_06_checkpoint_mapping(self): self.assertEqual(self.adapt("JOB_CHECKPOINTED", state="CHECKPOINTED").pushover_priority, 0)
    def test_07_switched_mapping(self): self.assertEqual(self.adapt("JOB_SWITCHED", state="READY").pushover_priority, 0)
    def test_08_idle_mapping(self): self.assertEqual(self.adapt("QUEUE_IDLE", state="READY").pushover_priority, -1)
    def test_09_blocked_mapping(self): self.assertEqual(self.adapt("QUEUE_BLOCKED", severity="WARN", state="BLOCKED").pushover_priority, 1)
    def test_10_critical_mapping(self): self.assertEqual(self.adapt("CRITICAL_STOP").pushover_priority, 2)
    def test_11_approval_high(self): self.assertEqual(self.adapt("JOB_WAITING_APPROVAL").pushover_priority, 1)
    def test_12_failed_high(self): self.assertEqual(self.adapt("JOB_FAILED_SAFE", severity="ERROR", state="FAILED_SAFE").pushover_priority, 1)
    def test_13_critical_candidate(self): self.assertTrue(self.adapt("CRITICAL_STOP").emergency_candidate)
    def test_14_noncritical_not_candidate(self): self.assertFalse(self.adapt().emergency_candidate)
    def test_15_approval_true(self): self.assertTrue(self.adapt("JOB_WAITING_APPROVAL").approval_required)
    def test_16_approval_false_contradiction(self): self.assertEqual(self.adapt("JOB_WAITING_APPROVAL", approval_required=False).notification_status, adapter.INVALID_INPUT)
    def test_17_nonapproval_true_contradiction(self): self.assertEqual(self.adapt(approval_required=True).notification_status, adapter.INVALID_INPUT)
    def test_18_critical_severity_mismatch(self): self.assertEqual(self.adapt("CRITICAL_STOP", severity="ERROR").notification_status, adapter.INVALID_INPUT)
    def test_19_unknown_adapter_version(self): self.assertIn("ADAPTER_VERSION_UNSUPPORTED", adapter.adapt_notification(event(), adapter_version="9").reason_codes)
    def test_20_unknown_event_version(self): self.assertIn("EVENT_VERSION_UNSUPPORTED", self.adapt(event_version="9").reason_codes)
    def test_21_unknown_event_type(self): self.assertIn("EVENT_TYPE_UNKNOWN", self.adapt("UNKNOWN").reason_codes)
    def test_22_unknown_severity(self): self.assertIn("SEVERITY_UNKNOWN", self.adapt(severity="UNKNOWN").reason_codes)
    def test_23_malformed_state(self): self.assertIn("STATE_MALFORMED", self.adapt(state="UNKNOWN").reason_codes)
    def test_24_missing_key(self):
        value = event(); value.pop("job_id"); self.assertIn("EVENT_SCHEMA_INVALID", adapter.adapt_notification(value).reason_codes)
    def test_25_unexpected_key(self): self.assertIn("EVENT_SCHEMA_INVALID", self.adapt(extra=True).reason_codes)
    def test_26_url_field_reject(self): self.assertEqual(self.adapt(job_id="https://example.invalid").notification_status, adapter.INVALID_INPUT)
    def test_27_token_field_reject(self): self.assertEqual(self.adapt(job_type="api_token").notification_status, adapter.INVALID_INPUT)
    def test_28_user_key_field_reject(self): self.assertEqual(self.adapt(job_type="user_key_secret").notification_status, adapter.INVALID_INPUT)
    def test_29_credential_field_reject(self): self.assertEqual(self.adapt(job_type="credential").notification_status, adapter.INVALID_INPUT)
    def test_30_raw_exception_reject(self): self.assertEqual(self.adapt(summary_code="RAW_EXCEPTION").notification_status, adapter.INVALID_INPUT)
    def test_31_traceback_reject(self): self.assertEqual(self.adapt(job_type="traceback").notification_status, adapter.INVALID_INPUT)
    def test_32_title_pattern_reject(self): self.assertEqual(self.adapt(job_type="private_title").notification_status, adapter.INVALID_INPUT)
    def test_33_content_id_reject(self): self.assertEqual(self.adapt(job_type="content_id").notification_status, adapter.INVALID_INPUT)
    def test_34_product_id_reject(self): self.assertEqual(self.adapt(job_type="product_id").notification_status, adapter.INVALID_INPUT)
    def test_35_windows_path_reject(self): self.assertEqual(self.adapt(job_id="C:/private").notification_status, adapter.INVALID_INPUT)
    def test_36_posix_path_reject(self): self.assertEqual(self.adapt(job_id="/private").notification_status, adapter.INVALID_INPUT)
    def test_37_output_exact_allowlist(self): self.assertEqual(set(self.adapt().to_dict()), adapter.OUTPUT_FIELDS)
    def test_38_no_secret_in_output(self): self.assertNotIn("job-a", repr(self.adapt().to_dict()))
    def test_39_deterministic_title(self): self.assertEqual(self.adapt(job_id="one").title, self.adapt(job_id="two").title)
    def test_40_deterministic_message(self): self.assertEqual(self.adapt(job_id="one").message, self.adapt(job_id="two").message)
    def test_41_deterministic_reasons(self): self.assertEqual(self.adapt().reason_codes, ("SAFE_NOTIFICATION_READY",))
    def test_42_message_limit(self):
        with mock.patch.dict(adapter.MAPPINGS, {"JOB_COMPLETED": (0, "NORMAL", "DATA LAB", "x" * 513)}):
            self.assertIn("MESSAGE_TOO_LONG", self.adapt().reason_codes)
    def test_43_title_limit(self):
        with mock.patch.dict(adapter.MAPPINGS, {"JOB_COMPLETED": (0, "NORMAL", "x" * 101, "Safe")}):
            self.assertIn("TITLE_TOO_LONG", self.adapt().reason_codes)
    def test_44_internal_exception_safe(self):
        with mock.patch.object(adapter, "_event_dict", side_effect=RuntimeError("secret traceback")):
            result = adapter.adapt_notification(event())
        self.assertEqual(result.reason_codes, ("INTERNAL_ADAPTER_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))
    def test_45_delivery_approval(self): self.assertEqual(self.adapt("JOB_WAITING_APPROVAL").delivery_class, "IMMEDIATE")
    def test_46_delivery_critical(self): self.assertEqual(self.adapt("CRITICAL_STOP").delivery_class, "IMMEDIATE")
    def test_47_delivery_completed(self): self.assertEqual(self.adapt().delivery_class, "NORMAL")
    def test_48_delivery_started(self): self.assertEqual(self.adapt("JOB_STARTED", state="RUNNING").delivery_class, "SUPPRESSIBLE")
    def test_49_switched_suppressible(self): self.assertEqual(self.adapt("JOB_SWITCHED", state="READY").delivery_class, "SUPPRESSIBLE")
    def test_50_checkpoint_suppressible(self): self.assertEqual(self.adapt("JOB_CHECKPOINTED", state="CHECKPOINTED").delivery_class, "SUPPRESSIBLE")
    def test_51_idle_suppressible(self): self.assertEqual(self.adapt("QUEUE_IDLE", state="READY").delivery_class, "SUPPRESSIBLE")
    def test_52_no_network_symbols(self):
        source = (ROOT / "scripts" / "pushover_notification_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("requests", source); self.assertNotIn("urlopen", source)
    def test_53_no_env_read_symbols(self):
        source = (ROOT / "scripts" / "pushover_notification_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("getenv", source); self.assertNotIn("dotenv", source)
    def test_54_does_not_mutate_event(self):
        value = event(); original = deepcopy(value); adapter.adapt_notification(value); self.assertEqual(value, original)
    def test_55_queue_event_accepted(self):
        import unattended_job_queue as queue
        value = queue.create_event(**event()); self.assertEqual(adapter.adapt_notification(value).notification_status, adapter.READY)
    def test_56_non_mapping_rejected(self): self.assertIn("EVENT_CONTRACT_INVALID", adapter.adapt_notification(None).reason_codes)
    def test_57_bad_timestamp_rejected(self): self.assertIn("OCCURRED_AT_INVALID", self.adapt(occurred_at="today").reason_codes)
    def test_58_nonboolean_approval_rejected(self): self.assertIn("APPROVAL_FLAG_MALFORMED", self.adapt(approval_required=0).reason_codes)
    def test_59_bad_job_id_type(self): self.assertIn("JOB_ID_INVALID", self.adapt(job_id=1).reason_codes)
    def test_60_bad_summary_code(self): self.assertIn("SUMMARY_CODE_INVALID", self.adapt(summary_code="lowercase").reason_codes)
    def test_61_ready_contract(self): self.assertEqual(self.adapt().notification_status, adapter.READY)
    def test_62_invalid_contract_is_bounded(self): self.assertEqual(set(self.adapt(extra=True).to_dict()), adapter.OUTPUT_FIELDS)


if __name__ == "__main__":
    unittest.main()
