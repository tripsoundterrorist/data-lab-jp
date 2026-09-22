from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canary_plan as plan_module
import affiliate_cta_canary_preflight as preflight


NOW = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)


def public_id(index):
    return f"itm_{index:024x}"


def visible_payload(content_id):
    return {
        "expected_content_id": content_id,
        "observed_at": NOW,
        "call_status": "success",
        "error_class": None,
        "source_status_code": 200,
        "result_count": 1,
        "items": [{"content_id": content_id, "affiliate_link_present": True}],
    }


class AffiliateCtaCanaryPreflightTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_module.current_plan()
        self.ids = tuple(public_id(index) for index in range(10))
        self.mapping = {value: f"cid{index}" for index, value in enumerate(self.ids)}

    def execute(self, **overrides):
        values = {
            "public_ids": self.ids,
            "as_of": NOW,
            "execution_authorized": True,
            "one_shot": True,
            "resolve_content_id": self.mapping.get,
            "fetch_sanitized_item_payload": visible_payload,
            "plan": self.plan,
        }
        values.update(overrides)
        return preflight.run_preflight(**values)

    def test_ten_verified_items_produce_review_only_counts(self):
        result = self.execute()
        self.assertEqual(result.status, preflight.READY)
        self.assertEqual(result.lookup_attempt_count, 10)
        self.assertEqual(result.api_request_attempt_count, 10)
        self.assertEqual(result.selected_count, 10)
        self.assertFalse(result.identifiers_exposed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.cta_activation_allowed)
        self.assertFalse(result.d1_write_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertNotIn("itm_", str(result.to_dict()))
        self.assertNotIn("cid", str(result.to_dict()))

    def test_default_or_missing_explicit_approval_never_invokes_callbacks(self):
        calls = []
        result = self.execute(
            execution_authorized=False,
            resolve_content_id=lambda value: calls.append(value),
            fetch_sanitized_item_payload=lambda value: calls.append(value),
        )
        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertEqual(calls, [])
        self.assertEqual(result.api_request_attempt_count, 0)

    def test_rate_limit_stops_remaining_requests(self):
        calls = []
        def fetch(content_id):
            calls.append(content_id)
            return {
                "expected_content_id": content_id,
                "observed_at": NOW,
                "call_status": "failure",
                "error_class": "rate_limited",
                "source_status_code": 429,
                "result_count": None,
                "items": [],
            }
        result = self.execute(fetch_sanitized_item_payload=fetch)
        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertTrue(result.rate_limit_stop)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.api_request_attempt_count, 1)

    def test_unresolved_item_blocks_before_request(self):
        calls = []
        result = self.execute(
            resolve_content_id=lambda _value: None,
            fetch_sanitized_item_payload=lambda value: calls.append(value),
        )
        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertEqual(calls, [])
        self.assertEqual(result.api_request_attempt_count, 0)

    def test_fetch_exception_fails_closed_without_retry(self):
        def fail(_value):
            raise RuntimeError("redacted")
        result = self.execute(fetch_sanitized_item_payload=fail)
        self.assertEqual(result.status, preflight.FAIL_CLOSED)
        self.assertEqual(result.api_request_attempt_count, 1)
        self.assertNotIn("redacted", str(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
