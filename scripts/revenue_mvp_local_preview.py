"""Build a validated Revenue MVP preview bundle under the OS temp root."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from typing import Any

from publication_artifact_validator import PASS, validate_artifacts
from revenue_mvp_deployment_preflight import _read_candidate


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
LOCAL_PREVIEW_READY = "LOCAL_PREVIEW_READY"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class PreviewResult:
    version: str
    status: str
    shell_file_count: int
    candidate_item_count: int | None
    candidate_shard_count: int
    local_preview_only: bool
    publication_allowed: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _load_static_builder() -> Any:
    path = ROOT / "scripts" / "build-static-site.py"
    spec = importlib.util.spec_from_file_location("local_preview_static_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("static builder unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_new_output(path: Path) -> Path:
    output = path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    output.relative_to(temp_root)
    if output == temp_root or output.exists() or output.parent.is_symlink():
        raise ValueError("unsafe preview output")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def build_preview(artifact_directory: Path, output_directory: Path) -> PreviewResult:
    staging: Path | None = None
    try:
        output = _safe_new_output(output_directory)
        candidate = _read_candidate(artifact_directory)
        validation = validate_artifacts(candidate)
        manifest = json.loads(candidate["manifest.json"])
        if (
            validation.artifact_validation != PASS
            or manifest.get("publication_status") != "local_validation_only"
            or not manifest.get("rights_review_required")
        ):
            raise ValueError("candidate not eligible for local preview")
        builder = _load_static_builder()
        root = builder.resolve_repo_root(ROOT)
        shell = builder.collect_sources(root)
        builder.validate_files(shell, builder.read_known_secret_values(root))
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
        for name, content in shell.items():
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        for name, content in candidate.items():
            destination = staging / "data" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        (staging / "robots.txt").write_text(
            "User-agent: *\nDisallow: /\n", encoding="utf-8"
        )
        os.replace(staging, output)
        staging = None
        return PreviewResult(
            VERSION, LOCAL_PREVIEW_READY, len(shell), validation.item_count,
            validation.shard_count, True, False, False,
            ("LOCAL_PREVIEW_READY", "PUBLICATION_REMAINS_BLOCKED"),
        )
    except Exception:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        return PreviewResult(
            VERSION, FAIL_CLOSED, 0, None, 0, True, False, False,
            ("LOCAL_PREVIEW_BUILD_ERROR",),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a non-publishable local preview.")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_preview(args.artifact_dir, args.output)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == LOCAL_PREVIEW_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
