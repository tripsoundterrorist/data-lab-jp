from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run-category-collector-task.ps1"


class CategoryCollectionTaskWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WRAPPER.read_text(encoding="utf-8")

    def test_live_run_requires_health_check(self):
        self.assertIn('"scripts\\category_collection_health.py"', self.source)
        self.assertIn('throw "HEALTH_CHECK_MISSING"', self.source)
        self.assertIn("if (-not $DryRun -and $code -eq 0)", self.source)

    def test_health_failure_becomes_task_failure(self):
        self.assertIn("$healthCode = $LASTEXITCODE", self.source)
        self.assertIn("if ($healthCode -ne 0) { $code = $healthCode }", self.source)
        self.assertRegex(self.source, r"(?m)^exit \$code$")

    def test_health_output_is_appended_to_same_log(self):
        self.assertIn("Tee-Object -FilePath $LogPath -Append", self.source)


if __name__ == "__main__":
    unittest.main()
