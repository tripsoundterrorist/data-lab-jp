from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_route_failure_notification_dry_run as subject


TIME = "2026-10-02T00:00:00Z"


def wrapper(revalidation="COMPLETED", health="HEALTHY"):
    return {
        "version": "0.2",
        "revalidation": {"status": revalidation, "mode": "LIVE"},
        "public_route_health": {
            "status": health, "external_write_performed": False,
        },
    }


class AffiliateRouteFailureNotificationDryRunTests(unittest.TestCase):
    def test_healthy_is_suppressed_without_credential_read(self):
        reads = []
        result = subject.run(
            wrapper(), occurred_at=TIME,
            credential_loader=lambda: (reads.append(True), ("x", "y"))[1],
        )
        self.assertEqual("SUPPRESSED_HEALTHY", result.status)
        self.assertEqual([], reads)
        self.assertFalse(result.delivery_attempted)
        self.assertFalse(result.external_send_performed)

    def test_failure_validates_credentials_without_send(self):
        result = subject.run(
            wrapper(health="FAILED_SAFE"), occurred_at=TIME,
            credential_loader=lambda: ("fixture-user", "fixture-app"),
        )
        self.assertEqual("READY_NO_SEND", result.status)
        self.assertEqual("DRY_RUN_READY", result.sender_status)
        self.assertTrue(result.credential_presence_ok)
        self.assertFalse(result.delivery_attempted)
        self.assertFalse(result.external_send_performed)

    def test_missing_credentials_or_bad_input_fails_closed(self):
        missing = subject.run(
            wrapper(revalidation="FAILED_SAFE"), occurred_at=TIME,
            credential_loader=lambda: (None, None),
        )
        self.assertEqual("FAILED_SAFE", missing.status)
        self.assertFalse(missing.external_send_performed)
        invalid = subject.run({}, occurred_at=TIME)
        self.assertEqual("FAILED_SAFE", invalid.status)


if __name__ == "__main__":
    unittest.main()
