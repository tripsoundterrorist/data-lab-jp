from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_route_failure_notification_live as subject
from notification_ledger import NotificationLedger


def wrapper(health="FAILED_SAFE"):
    return {
        "version": "0.2",
        "revalidation": {"status": "COMPLETED", "mode": "LIVE"},
        "public_route_health": {
            "status": health, "external_write_performed": False,
        },
    }


class Transport:
    def __init__(self):
        self.calls = 0
    def __call__(self, _endpoint, _payload, _timeout):
        self.calls += 1
        return {"status": 1}


class AffiliateRouteFailureNotificationLiveTests(unittest.TestCase):
    def execute(self, payload, day="2026-10-02", ledger=None, transport=None):
        return subject.run(
            payload, incident_day_utc=day,
            credential_loader=lambda: ("fixture-user", "fixture-app"),
            transport=transport or Transport(), ledger=ledger,
        )

    def test_healthy_suppresses_without_send(self):
        transport = Transport()
        result = self.execute(wrapper("HEALTHY"), transport=transport)
        self.assertEqual("SUPPRESSED_HEALTHY", result.status)
        self.assertEqual(0, transport.calls)
        self.assertFalse(result.external_send_performed)

    def test_failure_delivers_once_and_same_day_duplicate_is_suppressed(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = NotificationLedger(Path(folder) / "ledger.json")
            ledger.path.write_text("[]\n", encoding="utf-8")
            transport = Transport()
            first = self.execute(wrapper(), ledger=ledger, transport=transport)
            second = self.execute(wrapper(), ledger=ledger, transport=transport)
        self.assertEqual("DELIVERED", first.status)
        self.assertTrue(first.delivery_succeeded)
        self.assertEqual("DUPLICATE_SUPPRESSED", second.status)
        self.assertEqual(1, transport.calls)

    def test_next_day_is_new_bounded_notification(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = NotificationLedger(Path(folder) / "ledger.json")
            ledger.path.write_text("[]\n", encoding="utf-8")
            transport = Transport()
            first = self.execute(wrapper(), day="2026-10-02", ledger=ledger, transport=transport)
            second = self.execute(wrapper(), day="2026-10-03", ledger=ledger, transport=transport)
        self.assertEqual("DELIVERED", first.status)
        self.assertEqual("DELIVERED", second.status)
        self.assertEqual(2, transport.calls)


if __name__ == "__main__":
    unittest.main()
