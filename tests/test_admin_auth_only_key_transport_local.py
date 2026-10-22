"""Offline transport verification; missing runtime/dependency must fail, not skip."""
from pathlib import Path
import ast
import json
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "runtime-candidates" / "admin-auth-only-jose"
TRANSPORT = PACKAGE / "admin-auth-only-key-transport-local.mjs"
HARNESS = PACKAGE / "admin_auth_only_key_transport_local_harness.mjs"


def supports_node_version(value):
    match = re.fullmatch(r"v(22|24)\.(\d+)\.(\d+)", value.strip())
    return bool(match and (match[1] == "24" or int(match[2]) >= 12))


def successful_tap(result):
    """Require actual passing cases; never turn missing output into a green run."""
    if result.returncode != 0:
        return False
    counts = {}
    for name in ("tests", "pass", "fail", "skipped", "cancelled", "todo"):
        matches = re.findall(rf"(?m)^# {name} (\d+)\s*$", result.stdout)
        if len(matches) != 1:
            return False
        counts[name] = int(matches[0])
    return (counts["tests"] >= 28 and counts["pass"] == counts["tests"]
            and all(counts[name] == 0 for name in ("fail", "skipped", "cancelled", "todo")))


class AdminAuthOnlyKeyTransportLocalTests(unittest.TestCase):
    def test_supported_node_boundaries(self):
        for value in ("v22.12.0", "v22.23.3", "v24.0.0", "v24.19.0\n"):
            self.assertTrue(supports_node_version(value), value)
        for value in ("v20.19.0", "v22.11.9", "v23.0.0", "v25.0.0", "invalid", ""):
            self.assertFalse(supports_node_version(value), value)

    def test_tap_verdict_fails_closed(self):
        good = "# tests 28\n# pass 28\n# fail 0\n# skipped 0\n# cancelled 0\n# todo 0\n"
        result = lambda text, code=0: subprocess.CompletedProcess([], code, text, "")
        self.assertTrue(successful_tap(result(good)))
        for text in ("", good.replace("28", "27"), good.replace("# pass 28", "# pass 27"),
                     good + "# tests 28\n", good.replace("# fail 0\n", "")):
            self.assertFalse(successful_tap(result(text)), text)
        for name in ("fail", "skipped", "cancelled", "todo"):
            self.assertFalse(successful_tap(result(good.replace(f"# {name} 0", f"# {name} 1"))))
        self.assertFalse(successful_tap(result(good, 1)))

    def test_synthetic_harness_without_skips(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node 22.12+ (22.x) or 24.x required; do not skip")
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertTrue(supports_node_version(version.stdout), version.stdout)
        result = subprocess.run([node, "--test", "--test-reporter=tap", str(HARNESS)],
                                cwd=PACKAGE, capture_output=True, text=True, timeout=60, check=False)
        self.assertTrue(successful_tap(result), result.stdout + result.stderr)

    def test_reuses_only_existing_pinned_dependency(self):
        package = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((PACKAGE / "package-lock.json").read_text(encoding="utf-8"))
        self.assertIs(package["private"], True)
        self.assertEqual(package["dependencies"], {"jose": "6.2.13"})
        self.assertEqual(set(lock["packages"]), {"", "node_modules/jose"})
        source = TRANSPORT.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^import .*", source),
                         ["import {createAuthOnlyLocalWorker} from './admin-auth-only-jose-local-worker.mjs';"])

    def test_local_only_injected_transport_without_execution_wiring(self):
        source = TRANSPORT.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"export\s+default|\bfetch\s*\(")
        for forbidden in ("onRequest", "process.env", "console.", "createRemoteJWKSet",
                          "gtag(", "sendBeacon(", "DMM_API", "AFFILIATE_ITEM_LOOKUP"):
            self.assertNotIn(forbidden, source)
        for required in ("mode==='LOCAL_ONLY'", "typeof fetchPublicKeys==='function'",
                         "url!==endpoint", "issuer+'/cdn-cgi/access/certs'",
                         "redirect:'error'", "credentials:'omit'", "cache:'no-store'",
                         "new AbortController()", "structuredClone"):
            self.assertIn(required, source)
        candidate = (PACKAGE / "admin-auth-only-jose-local-worker.mjs").read_text(encoding="utf-8")
        self.assertIn("production_ready:false", candidate)
        self.assertIn("AUTHENTICATED_EXECUTION_DISABLED", candidate)

    def test_harness_is_synthetic_and_blocks_global_fetch(self):
        source = HARNESS.read_text(encoding="utf-8")
        for required in ("globalThis.fetch=", "REAL_NETWORK_FORBIDDEN",
                         "webcrypto.subtle.generateKey", "synthetic-owner@example.invalid"):
            self.assertIn(required, source)
        for forbidden in ("writeFile", "exportKey('jwk',pair.privateKey)", "process.env"):
            self.assertNotIn(forbidden, source)
        self.assertEqual(len(re.findall(r"(?m)^test\(", source)), 28)

    def test_not_in_static_build_or_deployment_configuration(self):
        module = ast.parse((ROOT / "scripts" / "build-static-site.py").read_text(encoding="utf-8"))
        assignments = [node.value for node in module.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "ALLOWLIST" for t in node.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertFalse(any("admin-auth-only-jose" in item
                             for item in ast.literal_eval(assignments[0])))
        configs = [ROOT / "wrangler.toml"]
        for pattern in ("wrangler.toml", "wrangler.jsonc"):
            configs.extend((ROOT / "deployment-candidates").rglob(pattern))
        for path in configs:
            if path.is_file():
                self.assertNotIn("admin-auth-only-jose", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
