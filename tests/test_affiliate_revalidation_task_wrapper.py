from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "run-affiliate-revalidation-task.ps1"


class AffiliateRevalidationTaskWrapperTests(unittest.TestCase):
    def setUp(self):
        self.text = PATH.read_text(encoding="utf-8")

    def test_wrapper_is_bounded_and_explicitly_live(self):
        self.assertIn("affiliate_local_lifecycle_revalidation.py", self.text)
        self.assertIn("affiliate_public_route_health.py", self.text)
        self.assertIn("affiliate_route_failure_notification_dry_run.py", self.text)
        self.assertIn("--execute --confirm LIVE_LOCAL_DMM_D1_REVALIDATION", self.text)
        self.assertIn("$RetentionDays = 30", self.text)
        self.assertNotIn("while (", self.text)
        self.assertNotIn("Start-Sleep", self.text)

    def test_wrapper_does_not_contain_secret_values_or_dangerous_repair(self):
        for forbidden in (
            "DMM_API_ID=", "DMM_AFFILIATE_ID=", "wrangler secret",
            "Unregister-ScheduledTask", "Remove-Item -Recurse", "taskkill",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_only_aggregate_runner_json_is_persisted(self):
        self.assertIn("ConvertFrom-Json", self.text)
        self.assertIn('logs\\affiliate-revalidation', self.text)
        self.assertIn('2>$null', self.text)
        self.assertIn("-Encoding UTF8", self.text)
        self.assertIn("public_route_health = $parsedHealth", self.text)
        self.assertIn("external_write_performed -eq $false", self.text)
        self.assertIn("if ($healthExitCode -ne 0) { exit 30 }", self.text)
        self.assertIn("failure_notification_dry_run = $parsedNotificationDry", self.text)
        self.assertIn("if ($notificationDryExitCode -ne 0) { exit 31 }", self.text)
        self.assertIn("external_send_performed -ne $false", self.text)
        self.assertNotIn("utf8NoBOM", self.text)


if __name__ == "__main__":
    unittest.main()
