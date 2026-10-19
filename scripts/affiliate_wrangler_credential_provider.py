"""Explicit, one-shot Wrangler bearer handoff; never invoked automatically.

Contract: https://developers.cloudflare.com/workers/wrangler/commands/general/#auth-token
Existing OAuth may be refreshed by Wrangler, including its normal credential
store update. Real invocation therefore requires approval; this is not a pure
read. No new login, permissions, credential-store parsing or D1 query is added.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HASH = re.compile(r"[0-9a-f]{64}\Z")
CHILD_OVERRIDES = {
    "WRANGLER_WRITE_LOGS": "false",
    "WRANGLER_SEND_METRICS": "false",
    "WRANGLER_SEND_ERROR_REPORTS": "false",
    "WRANGLER_LOG_SANITIZE": "true",
    "WRANGLER_LOG": "log",
    "WRANGLER_API_ENVIRONMENT": "production",
    "WRANGLER_NO_SKILLS_UPDATE_PROMPTS": "true",
    "DO_NOT_TRACK": "1",
    "CI": "true",
    "NODE_TLS_REJECT_UNAUTHORIZED": "1",
}
BLOCKED_ENV = frozenset((
    "NODE_OPTIONS", "NODE_DEBUG", "NODE_DEBUG_NATIVE", "NODE_V8_COVERAGE",
    "CLOUDFLARE_API_BASE_URL", "WRANGLER_AUTH_DOMAIN", "WRANGLER_AUTH_URL",
    "WRANGLER_TOKEN_URL", "WRANGLER_CLIENT_ID", "CLOUDFLARE_CLIENT_ID",
    "CLOUDFLARE_API_KEY", "CLOUDFLARE_EMAIL",
))


class CredentialUnavailable(ValueError):
    """Fixed non-sensitive operator reason only."""


def _digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _no_links(path):
    return not any(p.is_symlink() or getattr(p.lstat(), "st_file_attributes", 0) & 0x400
                   for p in (path, *path.parents))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_AUTH_FIELD")
        result[key] = value
    return result


class WranglerCredentialProvider:
    """No credential or process access at construction. No retries or token cache."""
    def __init__(self, node: Path, cli: Path, *, expected_node_sha256: str,
                 expected_cli_sha256: str, expected_bundle_sha256: str,
                 expected_version: str, approved: bool = False,
                 runner=subprocess.run, environment=None):
        self._node, self._cli = node, cli
        self._hashes = (expected_node_sha256, expected_cli_sha256, expected_bundle_sha256)
        self._version = expected_version
        self._approved, self._runner, self._environment = approved, runner, environment
        self._used = False
        self.process_attempts = 0

    def __repr__(self):
        return "WranglerCredentialProvider([REDACTED])"

    def _verify_identity(self):
        if (not isinstance(self._node, Path) or not isinstance(self._cli, Path)
                or not self._node.is_absolute() or not self._cli.is_absolute()
                or self._node.name.lower() not in ("node", "node.exe")
                or self._cli.name != "wrangler.js" or self._cli.parent.name != "bin"
                or type(self._version) is not str or re.fullmatch(r"\d+\.\d+\.\d+", self._version) is None
                or any(type(value) is not str or HASH.fullmatch(value) is None for value in self._hashes)):
            raise CredentialUnavailable("WRANGLER_AUTH_IDENTITY_INVALID")
        root = self._cli.parent.parent
        bundle, package = root / "wrangler-dist/cli.js", root / "package.json"
        paths = (self._node, self._cli, bundle, package)
        if any(not path.is_file() or not _no_links(path) for path in paths):
            raise CredentialUnavailable("WRANGLER_AUTH_FILES_INVALID")
        if tuple(_digest(path) for path in paths[:3]) != self._hashes:
            raise CredentialUnavailable("WRANGLER_AUTH_HASH_MISMATCH")
        if package.stat().st_size > 262144:
            raise CredentialUnavailable("WRANGLER_AUTH_PACKAGE_INVALID")
        metadata = json.loads(package.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if metadata.get("name") != "wrangler" or metadata.get("version") != self._version:
            raise CredentialUnavailable("WRANGLER_AUTH_VERSION_MISMATCH")

    def __call__(self):
        if self._approved is not True or self._used:
            raise CredentialUnavailable("WRANGLER_AUTH_APPROVAL_REQUIRED_OR_CONSUMED")
        self._used = True
        try:
            self._verify_identity()
            parent = os.environ if self._environment is None else self._environment
            child = {}
            for key, value in parent.items():
                if type(key) is not str or type(value) is not str:
                    raise CredentialUnavailable("WRANGLER_AUTH_ENVIRONMENT_INVALID")
                normalized = key.upper()
                if normalized in child and child[normalized] != value:
                    raise CredentialUnavailable("WRANGLER_AUTH_ENVIRONMENT_INVALID")
                child[normalized] = value
            if any(child.get(key) for key in BLOCKED_ENV):
                raise CredentialUnavailable("WRANGLER_AUTH_ENVIRONMENT_BLOCKED")
            child.update(CHILD_OVERRIDES)
            child.pop("WRANGLER_LOG_PATH", None)
            self.process_attempts = 1
            process = self._runner(
                [str(self._node), str(self._cli), "auth", "token", "--json"],
                cwd=self._cli.parent.parent, env=child, stdin=subprocess.DEVNULL,
                capture_output=True, shell=False, timeout=30, check=False,
            )
            if (process.returncode != 0 or type(process.stdout) is not bytes
                    or type(process.stderr) is not bytes or len(process.stdout) > 65536
                    or len(process.stderr) > 65536):
                raise CredentialUnavailable("WRANGLER_AUTH_UNAVAILABLE")
            payload = json.loads(process.stdout.decode("utf-8"), object_pairs_hook=_unique_object)
            if (type(payload) is not dict or set(payload) != {"type", "token"}
                    or payload["type"] not in ("oauth", "api_token")
                    or type(payload["token"]) is not str or not 1 <= len(payload["token"]) <= 4096
                    or any(not 33 <= ord(c) <= 126 for c in payload["token"])):
                raise CredentialUnavailable("WRANGLER_AUTH_OUTPUT_INVALID")
            return payload["token"]
        except CredentialUnavailable as error:
            # An injected runner must not smuggle sensitive exception text out.
            safe = {"WRANGLER_AUTH_IDENTITY_INVALID", "WRANGLER_AUTH_FILES_INVALID",
                    "WRANGLER_AUTH_HASH_MISMATCH", "WRANGLER_AUTH_PACKAGE_INVALID",
                    "WRANGLER_AUTH_VERSION_MISMATCH", "WRANGLER_AUTH_ENVIRONMENT_BLOCKED",
                    "WRANGLER_AUTH_ENVIRONMENT_INVALID", "WRANGLER_AUTH_UNAVAILABLE",
                    "WRANGLER_AUTH_OUTPUT_INVALID"}
            reason = str(error) if str(error) in safe else "WRANGLER_AUTH_FAILED_SAFE"
            raise CredentialUnavailable(reason) from None
        except Exception:
            # Do not propagate process output, exception text or timeout buffers.
            raise CredentialUnavailable("WRANGLER_AUTH_FAILED_SAFE") from None
