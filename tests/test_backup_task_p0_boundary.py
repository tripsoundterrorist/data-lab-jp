from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-backup-task.ps1"


class BackupTaskP0BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_category_backup_is_gated_after_revenue_backup_result(self):
        revenue_launch = cls_index(self.source, "& $PythonExecutable @backupArguments")
        category_gate = cls_index(self.source, "if ($backupScriptExitCode -eq 0)")
        category_check = cls_index(
            self.source,
            "Test-Path -LiteralPath $CategoryBackupScriptPath",
        )
        category_launch = cls_index(self.source, "& $PythonExecutable @categoryArguments")
        self.assertLess(revenue_launch, category_gate)
        self.assertLess(category_gate, category_check)
        self.assertLess(category_check, category_launch)

    def test_category_failure_does_not_erase_revenue_completion(self):
        self.assertIn('Write-SafeLog "wrapper_error=CATEGORY_BACKUP_SCRIPT_MISSING"', self.source)
        self.assertIn("if ($categoryExitCode -ne 0) { $backupScriptExitCode = $categoryExitCode }", self.source)
        self.assertNotIn('Write-SafeConsoleError -Code "CATEGORY_BACKUP_SCRIPT_MISSING"', self.source)


def cls_index(source: str, needle: str) -> int:
    index = source.find(needle)
    if index < 0:
        raise AssertionError(f"missing expected wrapper fragment: {needle}")
    return index


if __name__ == "__main__":
    unittest.main()
