from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "harden-category-collector-schedule.ps1"


class CategoryCollectorScheduleHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_is_dry_run_by_default_and_has_fixed_target(self):
        self.assertIn("[switch]$Apply", self.source)
        self.assertIn("DATA LAB Daily Category Collector", self.source)
        self.assertIn("run-category-collector-task.ps1", self.source)
        self.assertIn("if ($Apply)", self.source)

    def test_changes_only_resilience_settings(self):
        self.assertIn("StartWhenAvailable = $true", self.source)
        self.assertIn("WakeToRun = $true", self.source)
        self.assertIn("StopIfGoingOnBatteries = $false", self.source)
        self.assertIn("action_unchanged = $true", self.source)
        self.assertIn("trigger_unchanged = $true", self.source)

    def test_has_no_task_replacement_or_destructive_operations(self):
        for forbidden in (
            "Register-ScheduledTask", "Unregister-ScheduledTask",
            "New-ScheduledTask", "Remove-Item", "Stop-ScheduledTask",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
