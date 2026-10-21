"""Offline auth-only candidate: synthetic JWTs, no network or runtime wiring.

This is not Access login, an audited production JWT verifier, or deployment proof.
Production use requires a separately reviewed maintained verifier/runtime adapter.
No product revalidation modules, real identity values or bindings are introduced.
"""
from pathlib import Path
import ast
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "runtime-candidates" / "admin-auth-only-local-worker.mjs"
HARNESS = ROOT / "tests" / "admin_auth_only_local_worker_harness.mjs"


class AdminAuthOnlyLocalWorkerTests(unittest.TestCase):
    def test_synthetic_authentication_harness_runs_without_skipping(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required; auth verification cannot be skipped")
        result = subprocess.run(
            [node, "--test", "--test-reporter=tap", str(HARNESS)],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        count = re.search(r"(?m)^# tests (\d+)\s*$", result.stdout)
        self.assertIsNotNone(count, result.stdout)
        self.assertGreaterEqual(int(count.group(1)), 22)
        self.assertRegex(result.stdout, r"(?m)^# fail 0\s*$")
        self.assertRegex(result.stdout, r"(?m)^# skipped 0\s*$")

    def test_candidate_has_no_execution_or_deployment_entrypoint(self):
        source = CANDIDATE.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^import\s")
        self.assertNotRegex(source, r"export\s+default")
        self.assertNotIn("onRequest", source)
        self.assertIn("config.mode==='LOCAL_ONLY'", source)
        self.assertIn("production_ready:false", source)
        self.assertIn("AUTHENTICATED_EXECUTION_DISABLED", source)
        self.assertNotIn("two-route-", source)
        self.assertNotRegex(source, r"\bconsole\.")
        for forbidden in ("gtag(", "sendBeacon(", "process.env", "localStorage", "document.", "window."):
            self.assertNotIn(forbidden, source)

    def test_candidate_is_not_wired_to_deployment_or_site_build(self):
        module = ast.parse((ROOT / "scripts" / "build-static-site.py").read_text(encoding="utf-8"))
        allowlists = [
            node.value for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ALLOWLIST" for target in node.targets)
        ]
        self.assertEqual(len(allowlists), 1)
        allowlist = ast.literal_eval(allowlists[0])
        self.assertNotIn("runtime-candidates/admin-auth-only-local-worker.mjs", allowlist)
        self.assertFalse(any("admin-auth-only-local-worker" in path for path in allowlist))
        configs = [ROOT / "wrangler.toml"]
        configs.extend((ROOT / "deployment-candidates").rglob("wrangler.toml"))
        configs.extend((ROOT / "deployment-candidates").rglob("wrangler.jsonc"))
        for path in configs:
            if path.is_file():
                with self.subTest(path=path.relative_to(ROOT).as_posix()):
                    text = path.read_text(encoding="utf-8")
                    self.assertNotIn("admin-auth-only-local-worker", text)
                    self.assertNotIn("revalidation-admin.datalabx.jp", text)

    def test_harness_forbids_network_and_only_generates_synthetic_keys(self):
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("NETWORK_FORBIDDEN", source)
        self.assertIn("globalThis.fetch=", source)
        self.assertIn("crypto.subtle.generateKey", source)
        self.assertIn("synthetic-owner@example.invalid", source)
        self.assertNotIn("writeFile", source)
        self.assertNotIn("exportKey('jwk',pair.privateKey)", source)


if __name__ == "__main__":
    unittest.main()
