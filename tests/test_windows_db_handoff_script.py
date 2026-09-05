from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare-revenue-mvp-db-handoff.ps1"


class WindowsDatabaseHandoffScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_requires_explicit_database_path(self):
        self.assertRegex(
            self.text,
            r"\[Parameter\(Mandatory\)\]\s*\[string\]\$DatabasePath",
        )
        self.assertNotIn("data\\data-lab.db\"", self.text)

    def test_delegates_sqlite_audit_to_read_only_python_gate(self):
        self.assertIn('"revenue_mvp_db_audit.py"', self.text)
        self.assertIn("& $PythonExecutable $AuditScript --db $resolvedDatabase", self.text)
        self.assertIn('$audit.status -ne "READY"', self.text)
        self.assertIn("-not $audit.read_only", self.text)

    def test_hashes_before_and_after_audit(self):
        hashes = re.findall(
            r"Get-FileHash -LiteralPath \$resolvedDatabase -Algorithm SHA256",
            self.text,
        )
        self.assertEqual(len(hashes), 2)
        self.assertIn("DATABASE_CHANGED_DURING_HANDOFF_PREPARATION", self.text)

    def test_rejects_reparse_points(self):
        self.assertIn("[IO.FileAttributes]::ReparsePoint", self.text)
        self.assertIn("UNSAFE_DATABASE_ENTRY", self.text)

    def test_has_no_copy_upload_or_destructive_commands(self):
        forbidden = (
            "Copy-Item", "Move-Item", "Remove-Item", "Set-Content",
            "Invoke-WebRequest", "Invoke-RestMethod", "Start-Process",
        )
        for command in forbidden:
            self.assertNotIn(command, self.text)
        self.assertIn("upload_performed = $false", self.text)
        self.assertIn("copy_performed = $false", self.text)

    def test_safe_output_omits_database_and_python_paths(self):
        result_block = self.text.split("function Write-SafeResult", 1)[1].split("try {", 1)[0]
        self.assertNotIn("DatabasePath", result_block)
        self.assertNotIn("resolvedDatabase", result_block)
        self.assertNotIn("PythonExecutable", result_block)
        self.assertIn("expected_sha256", result_block)

    def test_errors_are_bounded(self):
        catch_block = self.text.rsplit("catch {", 1)[1]
        self.assertNotIn("$_", catch_block)
        self.assertIn("HANDOFF_PREPARATION_ERROR", catch_block)


if __name__ == "__main__":
    unittest.main()
