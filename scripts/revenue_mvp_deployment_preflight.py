"""Non-deploying, fail-closed preflight for the Revenue MVP bundle."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any

from publication_artifact_validator import validate_artifacts


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_VERSION = "0.1"
SHELL_VALIDATED = "SHELL_VALIDATED"
READY = "READY"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class DeploymentPreflightResult:
    preflight_version: str
    status: str
    production_build: str
    deployment_preflight: str
    public_data_state: str
    public_data_deployment_allowed: bool
    shell_file_count: int
    artifact_validation: str
    candidate_item_count: int | None
    candidate_shard_count: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _load_static_builder() -> Any:
    path = ROOT / "scripts" / "build-static-site.py"
    specification = importlib.util.spec_from_file_location(
        "revenue_mvp_static_builder", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("static builder unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _validate_shell(files: dict[str, bytes]) -> None:
    required_markers = {
        "_headers": (
            b"Content-Security-Policy:", b"frame-ancestors 'none'",
            b"X-Content-Type-Options: nosniff",
        ),
        "index.html": (b'https://datalabx.jp/', b'/analytics-consent.js'),
        "404.html": (b'content="noindex"',),
        "privacy.html": (b'Google Analytics', b'localStorage'),
        "robots.txt": (b'https://datalabx.jp/sitemap.xml',),
        "sitemap.xml": (b'https://datalabx.jp/',),
        "analytics-consent.js": (
            b'readChoice() !== GRANTED', b'if (!saveChoice(GRANTED)) return;',
        ),
    }
    for path, markers in required_markers.items():
        content = files.get(path, b"")
        if any(marker not in content for marker in markers):
            raise ValueError("required shell marker missing")
    if any(path == "data" or path.startswith("data/") for path in files):
        raise ValueError("public data mixed into shell")


def _read_candidate(directory: Path) -> dict[str, bytes]:
    root = directory.resolve(strict=True)
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    root.relative_to(temp_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("unsafe candidate root")
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise ValueError("unsafe candidate entry")
        relative = path.relative_to(root).as_posix()
        files[relative] = path.read_bytes()
    return files


def run_preflight(
    *,
    repo_root: Path = ROOT,
    artifact_directory: Path | None = None,
) -> DeploymentPreflightResult:
    """Inspect sources and optional candidate data; never build or deploy."""

    try:
        builder = _load_static_builder()
        root = builder.resolve_repo_root(repo_root)
        shell = builder.collect_sources(root)
        builder.validate_files(shell, builder.read_known_secret_values(root))
        _validate_shell(shell)
        base = {
            "preflight_version": PREFLIGHT_VERSION,
            "production_build": "PASS",
            "shell_file_count": len(shell),
        }
        if artifact_directory is None:
            return DeploymentPreflightResult(
                **base,
                status=SHELL_VALIDATED,
                deployment_preflight="NOT_EVALUATED_NO_PUBLIC_DATA",
                public_data_state="UNPUBLISHED",
                public_data_deployment_allowed=False,
                artifact_validation="NOT_RUN",
                candidate_item_count=None,
                candidate_shard_count=0,
                reason_codes=("PUBLIC_DATA_NOT_SUPPLIED",),
            )
        artifact = validate_artifacts(_read_candidate(artifact_directory))
        reasons = set(artifact.reason_codes)
        if artifact.artifact_validation != "PASS":
            reasons.add("ARTIFACT_VALIDATION_FAILED")
        if not artifact.publication_allowed:
            reasons.add("PUBLIC_DATA_GATE_CLOSED")
        allowed = artifact.artifact_validation == "PASS" and artifact.publication_allowed
        return DeploymentPreflightResult(
            **base,
            status=READY if allowed else BLOCKED,
            deployment_preflight="PASS" if allowed else "CLOSED",
            public_data_state="APPROVED_CANDIDATE" if allowed else "CANDIDATE_BLOCKED",
            public_data_deployment_allowed=allowed,
            artifact_validation=artifact.artifact_validation,
            candidate_item_count=artifact.item_count,
            candidate_shard_count=artifact.shard_count,
            reason_codes=tuple(sorted(reasons)) or ("DEPLOYMENT_PREFLIGHT_PASS",),
        )
    except Exception:
        return DeploymentPreflightResult(
            PREFLIGHT_VERSION, FAIL_CLOSED, "FAIL_CLOSED", "CLOSED",
            "UNKNOWN", False, 0, "NOT_RUN", None, 0,
            ("PREFLIGHT_INTERNAL_OR_INPUT_ERROR",),
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Revenue MVP deployment bundle without deploying it."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--artifact-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_preflight(
        repo_root=args.repo_root, artifact_directory=args.artifact_dir
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {SHELL_VALIDATED, READY} else 2


if __name__ == "__main__":
    raise SystemExit(main())
