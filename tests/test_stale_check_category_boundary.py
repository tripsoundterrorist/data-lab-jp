from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-stale-check-task.ps1"


def position(source: str, needle: str) -> int:
    value = source.find(needle)
    if value < 0:
        raise AssertionError(f"missing wrapper fragment: {needle}")
    return value


class StaleCheckCategoryBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_p0_stale_check_always_precedes_p1_health_check(self):
        p0_launch = position(self.source, "& $PythonExecutable @checkerArguments")
        p1_gate = position(self.source, "if ($checkerExitCode -eq 0)")
        p1_path_check = position(self.source, "Test-Path -LiteralPath $CategoryHealthPath")
        p1_launch = position(self.source, "& $PythonExecutable -B $CategoryHealthPath")
        self.assertLess(p0_launch, p1_gate)
        self.assertLess(p1_gate, p1_path_check)
        self.assertLess(p1_path_check, p1_launch)

    def test_p1_failure_is_visible_without_replacing_p0_execution(self):
        self.assertIn('Write-SafeLog "wrapper_error=CATEGORY_HEALTH_CHECK_MISSING"', self.source)
        self.assertIn(
            "if ($categoryHealthExitCode -ne 0) { $checkerExitCode = $categoryHealthExitCode }",
            self.source,
        )
        self.assertNotIn('Write-SafeConsoleError -Code "CATEGORY_HEALTH_CHECK_MISSING"', self.source)

    def test_health_output_uses_existing_private_log(self):
        self.assertIn("Tee-Object -FilePath $LogPath -Append", self.source)
        self.assertRegex(self.source, r"(?m)^exit \$checkerExitCode$")


if __name__ == "__main__":
    unittest.main()
