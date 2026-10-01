from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_cloudflare_dashboard_observation as subject  # noqa: E402


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def payload():
    return {
        "version": "0.1",
        "observed_at": "2026-10-01T11:30:00Z",
        "workers_requests_24h": 100,
        "workers_cpu_limit_errors_24h": 0,
        "d1_rows_read_24h": 100,
        "d1_rows_written_24h": 10,
        "d1_database_storage_bytes": 1000,
        "d1_account_storage_bytes": 1000,
        "active_cron_triggers": [],
    }


class CloudflareDashboardObservationTests(unittest.TestCase):
    def test_current_under_limit_observation_is_verified_without_authorizing_changes(self):
        result = subject.validate(payload(), now=NOW)
        self.assertEqual(result.status, subject.VERIFIED)
        self.assertTrue(result.cloudflare_free_plan_capacity_verified)
        self.assertTrue(result.unexpected_cron_absent)
        self.assertFalse(result.paid_plan_change_allowed)
        self.assertFalse(result.production_change_allowed)

    def test_any_active_cron_blocks(self):
        value = payload()
        value["active_cron_triggers"] = ["observed schedule: redacted"]
        result = subject.validate(value, now=NOW)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("UNEXPECTED_ACTIVE_CRON_PRESENT", result.reason_codes)

    def test_limit_and_cpu_findings_block(self):
        value = payload()
        value["workers_requests_24h"] = 100_000
        value["workers_cpu_limit_errors_24h"] = 1
        value["d1_rows_read_24h"] = 5_000_000
        result = subject.validate(value, now=NOW)
        self.assertIn("WORKERS_REQUEST_LIMIT_REACHED", result.reason_codes)
        self.assertIn("WORKERS_CPU_LIMIT_ERRORS_PRESENT", result.reason_codes)
        self.assertIn("D1_READ_LIMIT_REACHED", result.reason_codes)

    def test_stale_future_and_malformed_observations_fail_closed(self):
        cases = []
        stale = payload(); stale["observed_at"] = "2026-09-29T11:30:00Z"; cases.append(stale)
        future = payload(); future["observed_at"] = "2026-10-01T12:30:00Z"; cases.append(future)
        bad_count = payload(); bad_count["d1_rows_written_24h"] = -1; cases.append(bad_count)
        bad_cron = payload(); bad_cron["active_cron_triggers"] = [""]; cases.append(bad_cron)
        unknown = payload(); unknown["extra"] = 1; cases.append(unknown)
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(subject.validate(value, now=NOW).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
