from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "run-product-refresh-candidate-task.ps1"


class ProductRefreshCandidateTaskWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8")

    def test_pins_database_and_validates_candidate_hash(self):
        self.assertIn("Get-FileHash -LiteralPath $DatabasePath", self.source)
        self.assertIn("--expected-db-sha256 $databaseSha", self.source)
        self.assertIn("$candidateSha -ne $parsed.candidate_sha256", self.source)
        self.assertIn("--expected-count 100", self.source)

    def test_output_is_private_bounded_and_retained_for_seven_days(self):
        self.assertIn('$env:LOCALAPPDATA "DATA-LAB\\product-refresh-candidates"', self.source)
        self.assertIn("$RetentionDays = 7", self.source)
        self.assertIn("output inside repository", self.source)
        self.assertNotIn("while (", self.source)
        self.assertNotIn("Start-Sleep", self.source)

    def test_requires_all_write_boundaries_to_remain_closed(self):
        for expected in (
            "$parsed.publication_allowed -eq $false",
            "$parsed.production_write_performed -eq $false",
            "$parsed.d1_write_performed -eq $false",
        ):
            self.assertIn(expected, self.source)
        for forbidden in ("wrangler", "git push", "Invoke-WebRequest", "Invoke-RestMethod"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
