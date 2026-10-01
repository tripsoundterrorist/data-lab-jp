from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_cloudflare_dashboard_observation as dashboard  # noqa: E402
import revenue_mvp_expansion_resume_gate as subject  # noqa: E402
import revenue_mvp_revalidation_cadence_guard as cadence  # noqa: E402


def historical_cadence():
    events = tuple(
        cadence.RevalidationEvent(
            datetime(2026, 10, 1, hour, tzinfo=timezone.utc),
            "UNCONFIRMED", 0, cadence.UPSTREAM_REASON,
        )
        for hour in range(3)
    )
    return cadence.assess(events)


def verified_dashboard():
    return dashboard.validate({
        "version": "0.1",
        "observed_at": "2026-10-01T11:30:00Z",
        "workers_requests_24h": 1,
        "workers_cpu_limit_errors_24h": 0,
        "d1_rows_read_24h": 1,
        "d1_rows_written_24h": 1,
        "d1_database_storage_bytes": 1,
        "d1_account_storage_bytes": 1,
        "active_cron_triggers": [],
    }, now=datetime(2026, 10, 1, 12, tzinfo=timezone.utc))


class ExpansionResumeGateTests(unittest.TestCase):
    def test_verified_zero_cron_accounts_for_history_and_allows_preparation_only(self):
        result = subject.assess(historical_cadence(), verified_dashboard())
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.historical_cadence_detected)
        self.assertTrue(result.historical_cadence_accounted_for)
        self.assertTrue(result.next_batch_preparation_allowed)
        self.assertFalse(result.live_execution_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertTrue(result.explicit_live_approval_required)

    def test_missing_dashboard_observation_keeps_current_gate_blocked(self):
        result = subject.current_gate(observation_path=Path("missing-observation.json"))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.next_batch_preparation_allowed)
        self.assertIn(
            "CURRENT_CLOUDFLARE_OBSERVATION_UNVERIFIED", result.reason_codes
        )

    def test_active_cron_or_invalid_cadence_blocks(self):
        active = dashboard.DashboardObservation(
            "0.1", dashboard.BLOCKED, "2026-10-01T11:30:00Z",
            False, False, False, False, ("UNEXPECTED_ACTIVE_CRON_PRESENT",),
        )
        self.assertEqual(
            subject.assess(historical_cadence(), active).status, subject.BLOCKED
        )
        self.assertEqual(
            subject.assess(cadence.assess(None), verified_dashboard()).status,
            subject.BLOCKED,
        )

    def test_current_private_export_remains_blocked_without_dashboard_evidence(self):
        result = subject.current_gate()
        self.assertTrue(result.historical_cadence_detected)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.live_execution_allowed)


if __name__ == "__main__":
    unittest.main()
