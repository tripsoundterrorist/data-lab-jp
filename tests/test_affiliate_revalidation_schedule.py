from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "configure-affiliate-revalidation-schedule.ps1"


class AffiliateRevalidationScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8")

    def test_is_inert_by_default_and_daily_at_2000(self):
        self.assertIn("param([switch]$Apply)", self.source)
        self.assertIn('$PlannedTime = "20:00"', self.source)
        self.assertIn('$result.status = "READY_TO_CREATE"', self.source)
        self.assertIn("batch_size = 5", self.source)
        self.assertIn("production_write_performed_now = $false", self.source)

    def test_refuses_mismatch_and_prevents_overlap_or_retry_loop(self):
        self.assertIn("BLOCKED_EXISTING_TASK_MISMATCH", self.source)
        self.assertIn("BLOCKED_TASK_INSPECTION_FAILED", self.source)
        self.assertIn("Get-ScheduledTask -ErrorAction Stop", self.source)
        self.assertNotIn("Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue", self.source)
        self.assertIn("-MultipleInstances IgnoreNew", self.source)
        self.assertIn("automatic_retry_enabled = $false", self.source)
        for forbidden in (
            "Unregister-ScheduledTask", "-Force", "while (", "Start-Sleep",
            "DMM_API_ID=", "DMM_AFFILIATE_ID=", "wrangler secret",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
