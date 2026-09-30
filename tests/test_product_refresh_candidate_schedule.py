from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "configure-product-refresh-candidate-schedule.ps1"


class ProductRefreshCandidateScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8")

    def test_is_dry_run_by_default_at_1635(self):
        self.assertIn("param([switch]$Apply)", self.source)
        self.assertIn('$PlannedTime = "16:35"', self.source)
        self.assertIn('$result.status = "READY_TO_CREATE"', self.source)

    def test_refuses_to_replace_mismatch_and_never_publishes(self):
        self.assertIn("BLOCKED_EXISTING_TASK_MISMATCH", self.source)
        self.assertNotIn("Unregister-ScheduledTask", self.source)
        self.assertNotIn("-Force", self.source)
        self.assertIn("publication_allowed = $false", self.source)
        self.assertIn("production_write_performed = $false", self.source)


if __name__ == "__main__":
    unittest.main()
