"""Offline auth-check entry boundary. No live network or deployment."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime-candidates" / "admin-auth-only-jose"
HARNESS = PACKAGE / "admin_auth_check_entry_local_harness.mjs"
ENTRY = PACKAGE / "admin-auth-check-entry-local.mjs"

class AdminAuthCheckEntryLocalTests(unittest.TestCase):
    def test_offline_entry_boundary(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Supported Node runtime required; never skip")
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
        self.assertEqual(version.returncode, 0, version.stderr)
        match = re.fullmatch(r"v(22|24)\.(\d+)\.(\d+)", version.stdout.strip())
        self.assertTrue(match and (match[1] == "24" or int(match[2]) >= 12), version.stdout)
        result = subprocess.run([node, "--test", "--test-reporter=tap", str(HARNESS)],
                                cwd=PACKAGE, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        counts = {}
        for name in ("tests", "pass", "fail", "skipped", "cancelled", "todo"):
            values = re.findall(rf"(?m)^# {name} (\d+)\s*$", result.stdout)
            self.assertEqual(len(values), 1, result.stdout)
            counts[name] = int(values[0])
        self.assertGreaterEqual(counts["tests"], 11)
        self.assertEqual(counts["tests"], counts["pass"])
        for name in ("fail", "skipped", "cancelled", "todo"):
            self.assertEqual(counts[name], 0, result.stdout)

    def test_repo_relative_import_and_no_deployment_entry(self):
        source = ENTRY.read_text(encoding="utf-8")
        self.assertIn("from './admin-auth-only-key-transport-local.mjs'", source)
        self.assertNotIn("admin-auth-transport-integration-", source)
        self.assertNotRegex(source, r"export\s+default|process\.env|console\.")
        self.assertIn("production_ready:false", source)
        self.assertIn("url.pathname!=='/auth-check'", source)

    def test_harness_forbids_real_network_and_private_key_export(self):
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("globalThis.fetch=", source)
        self.assertIn("REAL_NETWORK_FORBIDDEN", source)
        self.assertNotIn("writeFile", source)
        self.assertNotIn("exportKey('jwk',pair.privateKey)", source)

if __name__ == "__main__":
    unittest.main()
