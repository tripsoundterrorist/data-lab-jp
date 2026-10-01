from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_route_failure_notification_candidate as subject


TIME = "2026-10-01T15:00:00Z"


def result(revalidation="COMPLETED", health="HEALTHY"):
    return {
        "version": "0.2",
        "revalidation": {"status": revalidation, "mode": "LIVE"},
        "public_route_health": {
            "status": health, "external_write_performed": False,
        },
    }


class AffiliateRouteFailureNotificationCandidateTests(unittest.TestCase):
    def test_healthy_result_is_suppressed(self):
        value = subject.build(result(), occurred_at=TIME)
        self.assertEqual("SUPPRESSED_HEALTHY", value.status)
        self.assertFalse(value.failure_detected)
        self.assertFalse(value.notification_ready)
        self.assertFalse(value.external_send_performed)

    def test_revalidation_or_route_failure_builds_safe_immediate_candidate(self):
        for payload in (
            result(revalidation="FAILED_SAFE"),
            result(health="FAILED_SAFE"),
        ):
            with self.subTest(payload=payload):
                value = subject.build(payload, occurred_at=TIME)
                self.assertEqual("READY_FOR_EXPLICIT_LIVE_SEND", value.status)
                self.assertTrue(value.failure_detected)
                self.assertTrue(value.event_created)
                self.assertTrue(value.notification_ready)
                self.assertEqual("IMMEDIATE", value.delivery_class)
                self.assertEqual(1, value.pushover_priority)
                self.assertFalse(value.external_send_performed)

    def test_malformed_or_unsafe_input_fails_closed_without_leak(self):
        payload = result()
        payload["product_id"] = "secret"
        value = subject.build(payload, occurred_at=TIME)
        self.assertEqual("FAILED_SAFE", value.status)
        rendered = json.dumps(value.to_dict()).casefold()
        for forbidden in ("secret", "product_id", "https://", "token"):
            self.assertNotIn(forbidden, rendered)
        self.assertFalse(value.external_send_performed)

    def test_invalid_timestamp_cannot_create_notification(self):
        value = subject.build(result(health="FAILED_SAFE"), occurred_at="invalid")
        self.assertEqual("FAILED_SAFE", value.status)
        self.assertTrue(value.failure_detected)
        self.assertFalse(value.notification_ready)


if __name__ == "__main__":
    unittest.main()
