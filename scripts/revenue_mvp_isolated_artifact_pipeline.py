"""Build and verify Revenue MVP public data in a new isolated directory."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any, Callable

from publication_artifact_validator import PASS, validate_artifacts
import revenue_mvp_db_handoff_preflight as db_handoff


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
LOCAL_ARTIFACT_VALIDATED = "LOCAL_ARTIFACT_VALIDATED"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class IsolatedArtifactResult:
    version: str
    status: str
    read_only_database: bool
    database_identity_verified: bool
    output_isolated: bool
    artifact_written: bool
    artifact_validation: str
    candidate_item_count: int | None
    candidate_shard_count: int
    publication_allowed: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _load_builder() -> Any:
    path = ROOT / "scripts" / "build-public-data.py"
    specification = importlib.util.spec_from_file_location(
        "isolated_public_data_builder", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("builder unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _safe_new_output(path: Path) -> Path:
    resolved = path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    resolved.relative_to(temp_root)
    if resolved == temp_root or resolved.exists() or resolved.parent.is_symlink():
        raise ValueError("output must be a new isolated directory")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _read_artifacts(directory: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("unsafe artifact entry")
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix != ".json":
            raise ValueError("unsafe artifact entry")
        files[path.relative_to(directory).as_posix()] = path.read_bytes()
    return files


def run_pipeline(
    database_path: Path,
    expected_sha256: str,
    output_directory: Path,
    *,
    as_of: datetime,
    generated_at: datetime,
    load_builder: Callable[[], Any] = _load_builder,
) -> IsolatedArtifactResult:
    """Validate identity, build locally, verify again, then write once."""

    try:
        output = _safe_new_output(output_directory)
        before = db_handoff.preflight(database_path, expected_sha256)
        if before.status != db_handoff.READY or not before.identity_verified:
            return IsolatedArtifactResult(
                VERSION, BLOCKED, True, False, True, False, "NOT_RUN",
                None, 0, False, False, tuple(before.reason_codes),
            )
        builder = load_builder()
        files, _summary = builder.build_documents(
            database_path, as_of, generated_at
        )
        memory_validation = validate_artifacts(files)
        if memory_validation.artifact_validation != PASS:
            return IsolatedArtifactResult(
                VERSION, BLOCKED, True, True, True, False,
                memory_validation.artifact_validation,
                memory_validation.item_count, memory_validation.shard_count,
                False, False, tuple(memory_validation.reason_codes),
            )
        after = db_handoff.preflight(database_path, expected_sha256)
        if after.status != db_handoff.READY or not after.identity_verified:
            return IsolatedArtifactResult(
                VERSION, BLOCKED, True, False, True, False, "PASS",
                memory_validation.item_count, memory_validation.shard_count,
                False, False, ("DATABASE_CHANGED_DURING_PIPELINE",),
            )
        builder.atomic_write(output, files)
        disk_validation = validate_artifacts(_read_artifacts(output))
        valid = disk_validation.artifact_validation == PASS
        return IsolatedArtifactResult(
            VERSION, LOCAL_ARTIFACT_VALIDATED if valid else BLOCKED,
            True, True, True, True, disk_validation.artifact_validation,
            disk_validation.item_count, disk_validation.shard_count,
            False, False,
            ("LOCAL_ARTIFACT_VALIDATED", "PUBLICATION_REVIEW_REQUIRED")
            if valid else tuple(disk_validation.reason_codes),
        )
    except Exception:
        return IsolatedArtifactResult(
            VERSION, FAIL_CLOSED, True, False, False, False, "NOT_RUN",
            None, 0, False, False, ("ISOLATED_ARTIFACT_PIPELINE_ERROR",),
        )


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO8601") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include UTC offset")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build verified Revenue MVP data in an isolated local directory."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=_timestamp)
    parser.add_argument("--generated-at", type=_timestamp)
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    result = run_pipeline(
        args.db, args.expected_sha256, args.output,
        as_of=args.as_of or now,
        generated_at=args.generated_at or now,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == LOCAL_ARTIFACT_VALIDATED else 2


if __name__ == "__main__":
    raise SystemExit(main())
