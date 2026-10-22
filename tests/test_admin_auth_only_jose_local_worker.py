"""Offline jose candidate; missing dependency/runtime is a failure, never a skip."""
from pathlib import Path
import ast
import json
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime-candidates" / "admin-auth-only-jose"
CANDIDATE = PACKAGE / "admin-auth-only-jose-local-worker.mjs"
HARNESS = PACKAGE / "admin_auth_only_jose_local_harness.mjs"


def supports_node_version(value):
    match = re.fullmatch(r"v(22|24)\.(\d+)\.(\d+)", value.strip())
    return bool(match and (match[1] == "24" or int(match[2]) >= 12))


class AdminAuthOnlyJoseLocalWorkerTests(unittest.TestCase):
    def test_supported_node_version_boundaries(self):
        for version in ("v22.12.0", "v22.23.3", "v24.0.0", "v24.19.0\n"):
            self.assertTrue(supports_node_version(version), version)
        for version in ("v20.19.0", "v22.11.9", "v23.0.0", "v25.0.0", "", "invalid"):
            self.assertFalse(supports_node_version(version), version)

    def test_synthetic_harness_without_skips(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node 22.12+ (22.x) or 24.x is required; do not skip")
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertTrue(supports_node_version(version.stdout), version.stdout)
        result = subprocess.run(
            [node, "--test", "--test-reporter=tap", str(HARNESS)],
            cwd=PACKAGE, capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        count = re.search(r"(?m)^# tests (\d+)\s*$", result.stdout)
        self.assertIsNotNone(count, result.stdout)
        self.assertGreaterEqual(int(count.group(1)), 26)
        for verdict in ("fail", "skipped", "cancelled"):
            self.assertRegex(result.stdout, rf"(?m)^# {verdict} 0\s*$")

    def test_dependency_is_exact_locked_and_private(self):
        package = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((PACKAGE / "package-lock.json").read_text(encoding="utf-8"))
        self.assertIs(package["private"], True)
        self.assertEqual(package["dependencies"], {"jose": "6.2.13"})
        self.assertEqual(set(package["scripts"]), {"test"})
        self.assertEqual(set(lock["packages"]), {"", "node_modules/jose"})
        entry = lock["packages"]["node_modules/jose"]
        self.assertEqual(entry["version"], "6.2.13")
        self.assertEqual(entry["resolved"], "https://registry.npmjs.org/jose/-/jose-6.2.13.tgz")
        self.assertEqual(entry["integrity"], "sha512-7TIg10ZE1x82YediN+lcrPNvGMKge9yFHQD+Qho/b8y2adfugU3AsvvHfxV0fzyFllT6l9xCjf4RWY9g/Z9PJQ==")
        self.assertEqual(entry["license"], "MIT")
        self.assertNotIn("hasInstallScript", entry)
        ignores = (PACKAGE / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("node_modules/", ignores)
        self.assertIn(".npm-cache/", ignores)

    def test_no_deployment_or_execution_wiring(self):
        source = CANDIDATE.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^import .*", source),
                         ["import {jwtVerify,createLocalJWKSet} from 'jose';"])
        self.assertNotRegex(source, r"export\s+default")
        for forbidden in ("onRequest", "process.env", "console.", "createRemoteJWKSet",
                          "gtag(", "sendBeacon(", "two-route-"):
            self.assertNotIn(forbidden, source)
        self.assertIn("production_ready:false", source)
        self.assertIn("AUTHENTICATED_EXECUTION_DISABLED", source)
        module = ast.parse((ROOT / "scripts" / "build-static-site.py").read_text(encoding="utf-8"))
        values = [node.value for node in module.body if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "ALLOWLIST" for t in node.targets)]
        self.assertEqual(len(values), 1)
        self.assertFalse(any("admin-auth-only-jose" in item for item in ast.literal_eval(values[0])))
        configs = [ROOT / "wrangler.toml"]
        configs.extend((ROOT / "deployment-candidates").rglob("wrangler.toml"))
        configs.extend((ROOT / "deployment-candidates").rglob("wrangler.jsonc"))
        for path in configs:
            if path.is_file():
                self.assertNotIn("admin-auth-only-jose", path.read_text(encoding="utf-8"))

    def test_harness_only_uses_synthetic_keys_and_no_network(self):
        source = HARNESS.read_text(encoding="utf-8")
        for required in ("globalThis.fetch=", "NETWORK_FORBIDDEN",
                         "crypto.subtle.generateKey", "synthetic-owner@example.invalid"):
            self.assertIn(required, source)
        for forbidden in ("writeFile", "exportKey('jwk',pair.privateKey)"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
