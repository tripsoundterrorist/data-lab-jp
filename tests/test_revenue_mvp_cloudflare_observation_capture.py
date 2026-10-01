from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_cloudflare_dashboard_observation as observation  # noqa: E402
import revenue_mvp_cloudflare_observation_capture as subject  # noqa: E402


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def raw():
    return {
        "workers_requests_24h": 10,
        "workers_cpu_limit_errors_24h": 0,
        "d1_rows_read_24h": 10,
        "d1_rows_written_24h": 1,
        "d1_database_storage_bytes": 1000,
        "d1_account_storage_bytes": 1000,
        "active_cron_triggers": [],
    }


class CloudflareObservationCaptureTests(unittest.TestCase):
    def test_complete_current_safe_input_builds_canonical_evidence(self):
        evidence, result = subject.build_evidence(raw(), observed_at=NOW, now=NOW)
        self.assertEqual(result.status, observation.VERIFIED)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["version"], "0.1")
        self.assertEqual(evidence["observed_at"], "2026-10-01T12:00:00Z")
        self.assertEqual(evidence["active_cron_triggers"], [])

    def test_active_cron_never_builds_evidence(self):
        value = raw(); value["active_cron_triggers"] = ["observed schedule"]
        evidence, result = subject.build_evidence(value, observed_at=NOW, now=NOW)
        self.assertIsNone(evidence)
        self.assertEqual(result.status, observation.BLOCKED)
        self.assertIn("UNEXPECTED_ACTIVE_CRON_PRESENT", result.reason_codes)

    def test_missing_stale_and_limit_inputs_never_build_evidence(self):
        missing = raw(); missing.pop("d1_rows_read_24h")
        stale_at = NOW - timedelta(days=2)
        limit = raw(); limit["workers_requests_24h"] = 100_000
        cases = ((missing, NOW), (raw(), stale_at), (limit, NOW))
        for value, observed_at in cases:
            with self.subTest(value=value, observed_at=observed_at):
                evidence, result = subject.build_evidence(
                    value, observed_at=observed_at, now=NOW
                )
                self.assertIsNone(evidence)
                self.assertNotEqual(result.status, observation.VERIFIED)


if __name__ == "__main__":
    unittest.main()
