from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pushover_notification_adapter as adapter  # noqa: E402
import pushover_sender as sender  # noqa: E402
import unattended_runtime as runtime  # noqa: E402


STATES = {"JOB_STARTED":"RUNNING","JOB_COMPLETED":"DONE","JOB_FAILED_SAFE":"FAILED_SAFE","JOB_WAITING_APPROVAL":"WAITING_APPROVAL","JOB_CHECKPOINTED":"CHECKPOINTED","JOB_SWITCHED":"READY","QUEUE_IDLE":"READY","QUEUE_BLOCKED":"BLOCKED","CRITICAL_STOP":"FAILED_SAFE"}


def event(event_type="JOB_COMPLETED", **changes):
    value={"event_version":"0.1","event_type":event_type,"job_id":"job-a","job_type":"static_validation","severity":"INFO","state":STATES.get(event_type,"DONE"),"approval_required":event_type=="JOB_WAITING_APPROVAL","summary_code":"SAFE_EVENT","occurred_at":"2026-08-27T00:00:00+09:00"}
    if event_type=="JOB_WAITING_APPROVAL": value["severity"]="WARN"
    if event_type=="JOB_FAILED_SAFE": value["severity"]="ERROR"
    if event_type=="QUEUE_BLOCKED": value["severity"]="WARN"
    if event_type=="CRITICAL_STOP": value["severity"]="CRITICAL"
    value.update(changes); return value


def credentials(): return "fixture-user", "fixture-app"


class Transport:
    def __init__(self,response=None,error=None): self.response={"status":1} if response is None else response; self.error=error; self.calls=[]
    def __call__(self,endpoint,payload,timeout):
        self.calls.append((endpoint,dict(payload),timeout))
        if self.error: raise self.error
        return self.response


class UnattendedRuntimeTests(unittest.TestCase):
    def execute(self,value=None,**kwargs):
        kwargs.setdefault("credential_loader",credentials)
        return runtime.process_notification(event() if value is None else value,**kwargs)

    def test_01_version(self): self.assertEqual(runtime.RUNTIME_VERSION,"0.1")
    def test_02_approval_selected(self): self.assertTrue(self.execute(event("JOB_WAITING_APPROVAL")).notification_selected)
    def test_03_failed_selected(self): self.assertTrue(self.execute(event("JOB_FAILED_SAFE")).notification_selected)
    def test_04_blocked_selected(self): self.assertTrue(self.execute(event("QUEUE_BLOCKED")).notification_selected)
    def test_05_completed_selected(self): self.assertTrue(self.execute().notification_selected)
    def test_06_started_suppressed(self): self.assertTrue(self.execute(event("JOB_STARTED")).notification_suppressed)
    def test_07_checkpoint_suppressed(self): self.assertTrue(self.execute(event("JOB_CHECKPOINTED")).notification_suppressed)
    def test_08_switched_suppressed(self): self.assertTrue(self.execute(event("JOB_SWITCHED")).notification_suppressed)
    def test_09_idle_suppressed(self): self.assertTrue(self.execute(event("QUEUE_IDLE")).notification_suppressed)
    def test_10_critical_blocked(self): self.assertTrue(self.execute(event("CRITICAL_STOP")).emergency_blocked)
    def test_11_dry_network_zero(self):
        t=Transport(); self.execute(transport=t); self.assertEqual(t.calls,[])
    def test_12_mock_runtime(self): self.assertTrue(self.execute(mode="MOCK_RUNTIME",transport=Transport()).delivery_succeeded)
    def test_13_live_explicit_required(self): self.assertEqual(self.execute(mode="LIVE_NOTIFICATION").runtime_status,"LIVE_NOTIFICATION_NOT_CONFIRMED")
    def test_14_live_false_network_zero(self):
        t=Transport(); self.execute(mode="LIVE_NOTIFICATION",transport=t); self.assertEqual(t.calls,[])
    def test_15_adapter_delegation(self):
        fn=mock.Mock(wraps=adapter.adapt_notification); self.execute(adapter_fn=fn); fn.assert_called_once()
    def test_16_sender_delegation(self):
        fn=mock.Mock(wraps=sender.send_notification); self.execute(sender_fn=fn); fn.assert_called_once()
    def test_17_no_priority_remap(self):
        captured={}
        def send(value,**kwargs): captured.update(value.to_dict()); return sender.send_notification(value,**kwargs)
        self.execute(event("JOB_WAITING_APPROVAL"),sender_fn=send); self.assertEqual(captured["pushover_priority"],1)
    def test_18_no_message_generation(self): self.assertNotIn("User approval is required",Path(runtime.__file__).read_text(encoding="utf-8"))
    def test_19_approval_immediate(self):
        captured={}
        def send(value,**kwargs): captured.update(value.to_dict()); return sender.send_notification(value,**kwargs)
        self.execute(event("JOB_WAITING_APPROVAL"),sender_fn=send); self.assertEqual(captured["delivery_class"],"IMMEDIATE")
    def test_20_completed_normal(self):
        captured={}
        def send(value,**kwargs): captured.update(value.to_dict()); return sender.send_notification(value,**kwargs)
        self.execute(sender_fn=send); self.assertEqual(captured["delivery_class"],"NORMAL")
    def test_21_notification_failure_safe(self): self.assertEqual(self.execute(mode="MOCK_RUNTIME",transport=Transport({"status":0})).runtime_status,"NOTIFICATION_FAILED_SAFE")
    def test_22_event_nonmutation(self):
        value=event(); original=deepcopy(value); self.execute(value); self.assertEqual(value,original)
    def test_23_sender_failure_no_rollback(self):
        value=event("JOB_FAILED_SAFE"); original=deepcopy(value); self.execute(value,mode="MOCK_RUNTIME",transport=Transport({"status":0})); self.assertEqual(value,original)
    def test_24_unknown_runtime_version(self): self.assertIn("RUNTIME_VERSION_UNSUPPORTED",self.execute(runtime_version="9").reason_codes)
    def test_25_unknown_event_version(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(event_version="9")).reason_codes)
    def test_26_malformed_event(self): self.assertIn("EVENT_CONTRACT_INVALID",self.execute([]).reason_codes)
    def test_27_unexpected_key(self): self.assertIn("EVENT_SCHEMA_INVALID",self.execute(event(extra=True)).reason_codes)
    def test_28_url_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_id="https://evil.invalid")).reason_codes)
    def test_29_token_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="api_token")).reason_codes)
    def test_30_user_key_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="user_key_secret")).reason_codes)
    def test_31_credential_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="credential")).reason_codes)
    def test_32_raw_exception_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(summary_code="RAW_EXCEPTION")).reason_codes)
    def test_33_traceback_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="traceback")).reason_codes)
    def test_34_content_id_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="content_id")).reason_codes)
    def test_35_product_id_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="product_id")).reason_codes)
    def test_36_title_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_type="private_title")).reason_codes)
    def test_37_path_reject(self): self.assertIn("QUEUE_EVENT_INVALID",self.execute(event(job_id="C:/private")).reason_codes)
    def test_38_safe_output_allowlist(self): self.assertEqual(set(self.execute().to_dict()),runtime.OUTPUT_FIELDS)
    def test_39_no_raw_adapter(self): self.assertNotIn("adapter",self.execute().to_dict())
    def test_40_no_raw_sender(self): self.assertNotIn("sender",self.execute().to_dict())
    def test_41_deterministic_reasons(self): self.assertEqual(self.execute().reason_codes,("DRY_RUN_VALIDATED",))
    def test_42_internal_exception_safe(self):
        with mock.patch.object(runtime,"_validate_event",side_effect=RuntimeError("secret traceback")): result=self.execute()
        self.assertEqual(result.reason_codes,("INTERNAL_RUNTIME_ERROR",)); self.assertNotIn("secret",repr(result.to_dict()))
    def test_43_duplicate_first(self):
        seen=set(); self.assertEqual(self.execute(seen_event_ids=seen).runtime_status,"NOTIFICATION_READY")
    def test_44_duplicate_second(self):
        seen=set(); self.execute(seen_event_ids=seen); self.assertEqual(self.execute(seen_event_ids=seen).runtime_status,"DUPLICATE_EVENT_SUPPRESSED")
    def test_45_duplicate_network_zero(self):
        seen=set(); self.execute(seen_event_ids=seen); t=Transport(); self.execute(seen_event_ids=seen,mode="MOCK_RUNTIME",transport=t); self.assertEqual(t.calls,[])
    def test_46_identity_deterministic(self): self.assertEqual(runtime.event_identity(event()),runtime.event_identity(deepcopy(event())))
    def test_47_missing_identity_closed(self): self.assertIsNone(runtime.event_identity({}))
    def test_48_approval_contradiction(self): self.assertIn("APPROVAL_FLAG_CONTRADICTORY",self.execute(event("JOB_WAITING_APPROVAL",approval_required=False)).reason_codes)
    def test_49_blocked_state_contradiction(self): self.assertIn("EVENT_STATE_CONTRADICTORY",self.execute(event("QUEUE_BLOCKED",state="READY")).reason_codes)
    def test_50_sender_status_malformed(self):
        bad={key:False for key in sender.OUTPUT_FIELDS}; bad["sender_status"]=None
        self.assertEqual(self.execute(sender_fn=lambda *a,**k:bad).runtime_status,"NOTIFICATION_FAILED_SAFE")
    def test_51_adapter_status_malformed(self):
        bad=adapter.adapt_notification(event()).to_dict(); bad["notification_status"]="INVALID_INPUT"
        self.assertIn("ADAPTER_RESULT_INVALID",self.execute(adapter_fn=lambda value:bad).reason_codes)
    def test_52_emergency_preserved(self): self.assertEqual(self.execute(event("CRITICAL_STOP")).runtime_status,"EMERGENCY_SEND_BLOCKED")
    def test_53_no_emergency_downgrade(self):
        captured={}
        def send(value,**kwargs): captured.update(value.to_dict()); return sender.send_notification(value,**kwargs)
        self.execute(event("CRITICAL_STOP"),sender_fn=send); self.assertEqual(captured["pushover_priority"],2)
    def test_54_suppressed_adapter_not_called(self):
        fn=mock.Mock(); self.execute(event("JOB_STARTED"),adapter_fn=fn); fn.assert_not_called()
    def test_55_suppressed_sender_not_called(self):
        fn=mock.Mock(); self.execute(event("QUEUE_IDLE"),sender_fn=fn); fn.assert_not_called()
    def test_56_selected_adapter_called(self):
        fn=mock.Mock(wraps=adapter.adapt_notification); self.execute(adapter_fn=fn); self.assertEqual(fn.call_count,1)
    def test_57_selected_sender_called(self):
        fn=mock.Mock(wraps=sender.send_notification); self.execute(sender_fn=fn); self.assertEqual(fn.call_count,1)
    def test_58_dry_not_attempted(self): self.assertFalse(self.execute().delivery_attempted)
    def test_59_mock_attempted(self): self.assertTrue(self.execute(mode="MOCK_RUNTIME",transport=Transport()).delivery_attempted)
    def test_60_live_attempted(self): self.assertTrue(self.execute(mode="LIVE_NOTIFICATION",live_notification_confirmed=True,transport=Transport()).delivery_attempted)
    def test_61_delivery_success(self): self.assertTrue(self.execute(mode="MOCK_RUNTIME",transport=Transport()).delivery_succeeded)
    def test_62_delivery_failure(self): self.assertFalse(self.execute(mode="MOCK_RUNTIME",transport=Transport({"status":0})).delivery_succeeded)
    def test_63_no_retry(self):
        t=Transport(error=TimeoutError()); self.execute(mode="MOCK_RUNTIME",transport=t); self.assertEqual(len(t.calls),1)
    def test_64_timeout_safe(self): self.assertEqual(self.execute(mode="MOCK_RUNTIME",transport=Transport(error=TimeoutError())).runtime_status,"NOTIFICATION_FAILED_SAFE")
    def test_65_network_safe(self): self.assertEqual(self.execute(mode="MOCK_RUNTIME",transport=Transport(error=ConnectionError())).runtime_status,"NOTIFICATION_FAILED_SAFE")
    def test_66_no_queue_selection(self): self.assertNotIn("select_next_job",Path(runtime.__file__).read_text(encoding="utf-8"))
    def test_67_no_risk_logic(self): self.assertNotIn("risk_class",Path(runtime.__file__).read_text(encoding="utf-8"))
    def test_68_no_adapter_mapping(self): self.assertNotIn("MAPPINGS",Path(runtime.__file__).read_text(encoding="utf-8"))
    def test_69_no_credential_loading(self): self.assertNotIn("load_credentials(",Path(runtime.__file__).read_text(encoding="utf-8"))
    def test_70_default_dry_run(self): self.assertEqual(self.execute().runtime_mode,"DRY_RUN")
    def test_71_runtime_nonmutation(self):
        value=event("JOB_FAILED_SAFE"); original=deepcopy(value); self.execute(value,mode="MOCK_RUNTIME",transport=Transport({"status":0})); self.assertEqual(value,original)
    def test_72_unknown_mode(self): self.assertIn("RUNTIME_MODE_INVALID",self.execute(mode="OTHER").reason_codes)
    def test_73_invalid_dedupe_store(self): self.assertIn("DEDUPLICATION_STORE_INVALID",self.execute(seen_event_ids=[]).reason_codes)
    def test_74_suppressed_recorded(self):
        seen=set(); self.execute(event("JOB_STARTED"),seen_event_ids=seen); self.assertEqual(len(seen),1)
    def test_75_sender_result_schema_invalid(self): self.assertIn("SENDER_RESULT_INVALID",self.execute(sender_fn=lambda *a,**k:{}).reason_codes)


if __name__ == "__main__": unittest.main()
