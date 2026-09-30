from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "run-product-refresh-assessment-task.ps1"


class ProductRefreshAssessmentTaskWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8")

    def test_wrapper_is_read_only_and_bounded(self):
        self.assertIn("revenue_mvp_product_refresh_rehearsal.py", self.source)
        self.assertIn("--expected-count 100", self.source)
        self.assertIn("$RetentionDays = 30", self.source)
        self.assertIn('[string]$RepoRoot = "C:\\github\\data-lab-jp"', self.source)
        self.assertNotIn("while (", self.source)
        self.assertNotIn("Start-Sleep", self.source)

    def test_wrapper_requires_closed_publication_boundary(self):
        self.assertIn("$parsed.publication_allowed -eq $false", self.source)
        self.assertIn("$parsed.production_write_performed -eq $false", self.source)
        self.assertIn('"READY_FOR_SEPARATE_REFRESH_CANDIDATE", "BLOCKED"', self.source)

    def test_wrapper_does_not_publish_or_touch_external_state(self):
        for forbidden in (
            "wrangler", "git push", "Invoke-WebRequest", "Invoke-RestMethod",
            "Register-ScheduledTask", "Unregister-ScheduledTask",
            "DMM_API_ID=", "DMM_AFFILIATE_ID=",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
