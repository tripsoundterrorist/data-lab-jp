"""Authentication-only Worker candidate: synthetic/offline tests, never deployment."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime-candidates" / "admin-auth-only-jose"

class AuthCheckWorkerCandidateTests(unittest.TestCase):
    def test_offline_worker_contract(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Supported Node required; never skip")
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
        self.assertEqual(version.returncode, 0, version.stderr)
        match = re.fullmatch(r"v(22|24)\.(\d+)\.(\d+)", version.stdout.strip())
        self.assertTrue(match and (match[1] == "24" or int(match[2]) >= 12), version.stdout)
        result = subprocess.run([node, "--test", "--test-reporter=tap",
                                 str(PACKAGE / "auth_check_worker_candidate_harness.mjs")],
                                cwd=PACKAGE, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        counts = {}
        for name in ("tests", "pass", "fail", "skipped", "cancelled", "todo"):
            values = re.findall(rf"(?m)^# {name} (\d+)\s*$", result.stdout)
            self.assertEqual(len(values), 1, result.stdout)
            counts[name] = int(values[0])
        self.assertGreaterEqual(counts["tests"], 23)
        self.assertEqual(counts["tests"], counts["pass"])
        for name in ("fail", "skipped", "cancelled", "todo"):
            self.assertEqual(counts[name], 0, result.stdout)

    def test_shared_cores_do_not_acquire_ambient_network_or_deployment_entrypoints(self):
        for name in ("access-assertion-verifier.mjs", "access-public-key-loader.mjs"):
            source = (PACKAGE / name).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"export\s+default|globalThis\.fetch|process\.env|console\.")
        verifier = (PACKAGE / "access-assertion-verifier.mjs").read_text(encoding="utf-8")
        self.assertIn("maxTokenAge:900", verifier)
        self.assertIn("clockTolerance:0", verifier)
        self.assertIn("payload.exp-payload.iat<=900", verifier)
        loader = (PACKAGE / "access-public-key-loader.mjs").read_text(encoding="utf-8")
        self.assertIn("timeoutMs=800", loader)
        self.assertIn("safeInteger(timeoutMs,1,800)", loader)
        self.assertIn("redirect:'error',credentials:'omit'", loader)

    def test_not_referenced_by_public_build_or_deployment_configs(self):
        module = ast.parse((ROOT / "scripts" / "build-static-site.py").read_text(encoding="utf-8"))
        allowlists = [n.value for n in module.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "ALLOWLIST" for t in n.targets)]
        self.assertEqual(len(allowlists), 1)
        self.assertFalse(any("admin-auth-only-jose" in p for p in ast.literal_eval(allowlists[0])))
        configs = [ROOT / "wrangler.toml"]
        for pattern in ("wrangler.toml", "wrangler.jsonc"):
            configs.extend((ROOT / "deployment-candidates").rglob(pattern))
        for config in configs:
            self.assertNotIn("admin-auth-only-jose", config.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
