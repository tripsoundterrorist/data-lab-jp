from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "configure-product-refresh-assessment-schedule.ps1"


class ProductRefreshAssessmentScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_is_dry_run_by_default_and_bounded_to_1630(self):
        self.assertIn("param([switch]$Apply)", self.source)
        self.assertIn("DATA LAB Daily Product Refresh Assessment", self.source)
        self.assertIn('$PlannedTime = "16:30"', self.source)
        self.assertIn('$result.status = "READY_TO_CREATE"', self.source)

    def test_refuses_to_replace_a_mismatched_existing_task(self):
        self.assertIn("BLOCKED_EXISTING_TASK_MISMATCH", self.source)
        self.assertNotIn("Unregister-ScheduledTask", self.source)
        self.assertNotIn("-Force", self.source)

    def test_keeps_publication_and_production_closed(self):
        self.assertIn("publication_allowed = $false", self.source)
        self.assertIn("production_write_performed = $false", self.source)
        for forbidden in (
            "wrangler", "git push", "Invoke-WebRequest", "Invoke-RestMethod",
            "DMM_API_ID=", "DMM_AFFILIATE_ID=",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_uses_existing_unattended_resilience_settings(self):
        for expected in (
            "-StartWhenAvailable", "-WakeToRun", "-AllowStartIfOnBatteries",
            "-DontStopIfGoingOnBatteries", "-ExecutionTimeLimit",
        ):
            self.assertIn(expected, self.source)


if __name__ == "__main__":
    unittest.main()
