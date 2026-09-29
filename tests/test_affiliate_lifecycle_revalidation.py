from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AffiliateLifecycleRevalidationTests(unittest.TestCase):
    def test_contract_is_bounded_fail_closed_and_secret_free(self):
        source = (ROOT / "runtime-candidates" / "affiliate-lifecycle-revalidation.mjs").read_text(encoding="utf-8")
        self.assertIn("LIMIT 5", source)
        self.assertIn("affiliate_enabled = 0", source)
        self.assertIn("verification_status = ?", source)
        self.assertIn("fetchAndDeliverDmmAffiliateUrl", source)
        self.assertNotIn("console.", source)
        self.assertNotIn("api_id:", source)
        self.assertNotIn("affiliate_id:", source)

    def test_schema_has_private_audit_event_table(self):
        migration = (ROOT / "runtime-candidates" / "affiliate-lifecycle-revalidation-schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE affiliate_lifecycle_revalidation_event", migration)
        self.assertIn("CHECK (outcome IN ('VALID', 'NOT_AVAILABLE', 'UNCONFIRMED'))", migration)
        for forbidden in ("affiliate_url", "content_id", "api_id", "affiliate_id"):
            self.assertNotIn(forbidden, migration.casefold())

    def test_node_harness(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "affiliate_lifecycle_revalidation_harness.mjs")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
