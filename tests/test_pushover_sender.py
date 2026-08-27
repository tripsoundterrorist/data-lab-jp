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


def notification(priority=0, delivery="NORMAL", **changes):
    value = {
        "adapter_version": "0.1", "notification_status": "READY",
        "pushover_priority": priority, "emergency_candidate": priority == 2,
        "delivery_class": delivery, "title": "DATA LAB — Completed",
        "message": "Job completed successfully.", "approval_required": False,
        "reason_codes": ["SAFE_NOTIFICATION_READY"],
    }
    value.update(changes)
    return value


def credentials(): return "fixture-user", "fixture-app"


class Transport:
    def __init__(self, response=None, error=None):
        self.response = {"status": 1} if response is None else response
        self.error = error
        self.calls = []

    def __call__(self, endpoint, payload, timeout):
        self.calls.append((endpoint, dict(payload), timeout))
        if self.error: raise self.error
        return self.response


class PushoverSenderTests(unittest.TestCase):
    def send(self, value=None, **kwargs):
        kwargs.setdefault("credential_loader", credentials)
        return sender.send_notification(notification() if value is None else value, **kwargs)

    def test_01_version(self): self.assertEqual(sender.SENDER_VERSION, "0.1")
    def test_02_default_dry_run(self): self.assertEqual(self.send().sender_status, "DRY_RUN_READY")
    def test_03_dry_high(self): self.assertEqual(self.send(notification(1)).sender_status, "DRY_RUN_READY")
    def test_04_dry_low(self): self.assertEqual(self.send(notification(-1)).sender_status, "DRY_RUN_READY")
    def test_05_dry_emergency_blocked(self): self.assertEqual(self.send(notification(2, "IMMEDIATE")).sender_status, "EMERGENCY_SEND_BLOCKED")
    def test_06_mock_normal(self): self.assertTrue(self.send(mode="MOCK_SEND", transport=Transport()).delivery_succeeded)
    def test_07_mock_high(self): self.assertTrue(self.send(notification(1), mode="MOCK_SEND", transport=Transport()).delivery_succeeded)
    def test_08_mock_completed(self): self.assertEqual(self.send(mode="MOCK_SEND", transport=Transport()).sender_status, "SEND_SUCCEEDED")
    def test_09_mock_approval(self): self.assertTrue(self.send(notification(1, "IMMEDIATE", approval_required=True), mode="MOCK_SEND", transport=Transport()).delivery_succeeded)
    def test_10_suppressible_default(self): self.assertEqual(self.send(notification(-1, "SUPPRESSIBLE")).sender_status, "SUPPRESSED")
    def test_11_suppressible_explicit(self): self.assertTrue(self.send(notification(-1, "SUPPRESSIBLE"), mode="MOCK_SEND", send_suppressible=True, transport=Transport()).delivery_succeeded)
    def test_12_missing_user(self): self.assertEqual(self.send(credential_loader=lambda: (None, "app")).sender_status, "CREDENTIAL_MISSING")
    def test_13_missing_app(self): self.assertEqual(self.send(credential_loader=lambda: ("user", None)).sender_status, "CREDENTIAL_MISSING")
    def test_14_empty_user(self): self.assertFalse(self.send(credential_loader=lambda: ("", "app")).credential_presence_ok)
    def test_15_empty_app(self): self.assertFalse(self.send(credential_loader=lambda: ("user", "")).credential_presence_ok)
    def test_16_credentials_not_output(self): self.assertNotIn("fixture", repr(self.send().to_dict()))
    def test_17_no_logger(self): self.assertFalse(hasattr(sender, "logger"))
    def test_18_unknown_sender_version(self): self.assertIn("SENDER_VERSION_UNSUPPORTED", self.send(sender_version="9").reason_codes)
    def test_19_unknown_adapter_version(self): self.assertIn("ADAPTER_VERSION_UNSUPPORTED", self.send(notification(adapter_version="9")).reason_codes)
    def test_20_malformed_result(self): self.assertIn("NOTIFICATION_CONTRACT_INVALID", self.send([]).reason_codes)
    def test_21_unexpected_key(self): self.assertIn("NOTIFICATION_SCHEMA_INVALID", self.send(notification(extra=True)).reason_codes)
    def test_22_unknown_priority(self): self.assertIn("PRIORITY_INVALID", self.send(notification(priority=None, emergency_candidate=False)).reason_codes)
    def test_23_priority_minus_three(self): self.assertIn("PRIORITY_INVALID", self.send(notification(priority=-3, emergency_candidate=False)).reason_codes)
    def test_24_priority_three(self): self.assertIn("PRIORITY_INVALID", self.send(notification(priority=3, emergency_candidate=False)).reason_codes)
    def test_25_emergency_mismatch_true(self): self.assertIn("EMERGENCY_FLAG_MISMATCH", self.send(notification(emergency_candidate=True)).reason_codes)
    def test_26_emergency_mismatch_false(self): self.assertIn("EMERGENCY_FLAG_MISMATCH", self.send(notification(2, emergency_candidate=False)).reason_codes)
    def test_27_priority_two_live_blocked(self): self.assertTrue(self.send(notification(2, "IMMEDIATE"), mode="LIVE_SEND", live_send_confirmed=True).emergency_blocked)
    def test_28_priority_two_network_zero(self):
        transport=Transport(); self.send(notification(2, "IMMEDIATE"), mode="LIVE_SEND", live_send_confirmed=True, transport=transport); self.assertEqual(transport.calls, [])
    def test_29_fixed_endpoint(self):
        transport=Transport(); self.send(mode="MOCK_SEND", transport=transport); self.assertEqual(transport.calls[0][0], sender.ENDPOINT)
    def test_30_post_only(self):
        with mock.patch.object(sender.request, "urlopen") as opened:
            response=mock.MagicMock(); response.status=200; response.read.return_value=b'{"status":1}'; opened.return_value.__enter__.return_value=response
            self.send(mode="LIVE_SEND", live_send_confirmed=True, transport=sender._default_transport)
            self.assertEqual(opened.call_args.args[0].method, "POST")
    def test_31_external_endpoint_reject(self): self.assertIn("NOTIFICATION_SCHEMA_INVALID", self.send(notification(endpoint="https://evil.invalid")).reason_codes)
    def test_32_timeout_configured(self):
        transport=Transport(); self.send(mode="MOCK_SEND", transport=transport); self.assertEqual(transport.calls[0][2], 10)
    def test_33_no_retry_success(self):
        transport=Transport(); self.send(mode="MOCK_SEND", transport=transport); self.assertEqual(len(transport.calls), 1)
    def test_34_no_retry_failure(self):
        transport=Transport(error=TimeoutError()); self.send(mode="MOCK_SEND", transport=transport); self.assertEqual(len(transport.calls), 1)
    def test_35_status_one_success(self): self.assertTrue(self.send(mode="MOCK_SEND", transport=Transport({"status": 1})).delivery_succeeded)
    def test_36_status_zero_fail(self): self.assertEqual(self.send(mode="MOCK_SEND", transport=Transport({"status": 0})).sender_status, "SEND_FAILED_SAFE")
    def test_37_malformed_response(self): self.assertEqual(self.send(mode="MOCK_SEND", transport=Transport("bad")).sender_status, "SEND_FAILED_SAFE")
    def test_38_timeout_safe(self): self.assertEqual(self.send(mode="MOCK_SEND", transport=Transport(error=TimeoutError("fixture-secret"))).sender_status, "SEND_FAILED_SAFE")
    def test_39_connection_safe(self): self.assertEqual(self.send(mode="MOCK_SEND", transport=Transport(error=ConnectionError())).sender_status, "SEND_FAILED_SAFE")
    def test_40_http_error_safe(self): self.assertEqual(self.send(mode="MOCK_SEND", transport=Transport(error=OSError())).sender_status, "SEND_FAILED_SAFE")
    def test_41_raw_response_absent(self): self.assertNotIn("response", self.send().to_dict())
    def test_42_request_id_absent(self): self.assertNotIn("request", repr(self.send(mode="MOCK_SEND", transport=Transport({"status": 1, "request": "fixture"})).to_dict()))
    def test_43_payload_absent(self): self.assertNotIn("payload", self.send().to_dict())
    def test_44_exact_output(self): self.assertEqual(set(self.send().to_dict()), sender.OUTPUT_FIELDS)
    def test_45_text_absent(self):
        result=repr(self.send().to_dict()); self.assertNotIn("Completed", result); self.assertNotIn("successfully", result)
    def test_46_env_contents_absent(self): self.assertNotIn("fixture-user", repr(self.send().to_dict()))
    def test_47_secret_exception_safe(self): self.assertNotIn("fixture-secret", repr(self.send(mode="MOCK_SEND", transport=Transport(error=RuntimeError("fixture-secret"))).to_dict()))
    def test_48_internal_exception_safe(self):
        with mock.patch.object(sender, "_contract", side_effect=RuntimeError("secret")): result=self.send()
        self.assertEqual(result.reason_codes, ("INTERNAL_SENDER_ERROR",))
    def test_49_input_nonmutation(self):
        value=notification(); original=deepcopy(value); self.send(value); self.assertEqual(value, original)
    def test_50_deterministic_reasons(self): self.assertEqual(self.send().reason_codes, ("NOTIFICATION_VALIDATED",))
    def test_51_dry_not_attempted(self): self.assertFalse(self.send().delivery_attempted)
    def test_52_mock_attempted(self): self.assertTrue(self.send(mode="MOCK_SEND", transport=Transport()).delivery_attempted)
    def test_53_live_attempted(self): self.assertTrue(self.send(mode="LIVE_SEND", live_send_confirmed=True, transport=Transport()).delivery_attempted)
    def test_54_success_true(self): self.assertTrue(self.send(mode="MOCK_SEND", transport=Transport()).delivery_succeeded)
    def test_55_failure_false(self): self.assertFalse(self.send(mode="MOCK_SEND", transport=Transport({"status": 0})).delivery_succeeded)
    def test_56_presence_true(self): self.assertTrue(self.send().credential_presence_ok)
    def test_57_presence_false(self): self.assertFalse(self.send(credential_loader=lambda: (None, None)).credential_presence_ok)
    def test_58_immediate_candidate(self): self.assertEqual(self.send(notification(1, "IMMEDIATE")).sender_status, "DRY_RUN_READY")
    def test_59_normal_candidate(self): self.assertEqual(self.send().sender_status, "DRY_RUN_READY")
    def test_60_suppressible_skipped(self): self.assertTrue(self.send(notification(-1, "SUPPRESSIBLE")).suppressible_skipped)
    def test_61_default_suppressible_false(self):
        transport=Transport(); self.send(notification(-1, "SUPPRESSIBLE"), mode="MOCK_SEND", transport=transport); self.assertEqual(transport.calls, [])
    def test_62_live_confirmation_required(self): self.assertEqual(self.send(mode="LIVE_SEND").sender_status, "LIVE_SEND_NOT_CONFIRMED")
    def test_63_live_false_network_zero(self):
        transport=Transport(); self.send(mode="LIVE_SEND", transport=transport); self.assertEqual(transport.calls, [])
    def test_64_queue_not_mutated(self):
        import unattended_job_queue as queue
        self.assertFalse(any(name.startswith("mutate") for name in dir(queue))); self.send()
    def test_65_adapter_object_accepted(self):
        value=adapter.adapt_notification({"event_version":"0.1","event_type":"JOB_COMPLETED","job_id":"job-a","job_type":"static_validation","severity":"INFO","state":"DONE","approval_required":False,"summary_code":"JOB_COMPLETED_SAFE","occurred_at":"2026-08-27T00:00:00+09:00"})
        self.assertEqual(self.send(value).sender_status, "DRY_RUN_READY")
    def test_66_unknown_mode(self): self.assertIn("SENDER_MODE_INVALID", self.send(mode="OTHER").reason_codes)
    def test_67_mock_requires_transport(self): self.assertIn("MOCK_TRANSPORT_REQUIRED", self.send(mode="MOCK_SEND").reason_codes)
    def test_68_unsafe_title(self): self.assertIn("NOTIFICATION_TEXT_UNSAFE", self.send(notification(title="https://evil.invalid")).reason_codes)
    def test_69_unsafe_message(self): self.assertIn("NOTIFICATION_TEXT_UNSAFE", self.send(notification(message="credential secret")).reason_codes)
    def test_70_nonready_adapter(self): self.assertIn("NOTIFICATION_NOT_READY", self.send(notification(notification_status="INVALID_INPUT")).reason_codes)


if __name__ == "__main__":
    unittest.main()
