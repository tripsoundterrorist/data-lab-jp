"""Read-only, one-command validation gate for Revenue MVP public-data candidates."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable

from publication_artifact_validator import validate_artifacts
from publication_gate import evaluate_publication_gate
from revenue_mvp_db_audit import audit_database, READY as DATABASE_READY


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
GATE_VERSION = "0.1"
LOCAL_CANDIDATE_VALIDATED = "LOCAL_CANDIDATE_VALIDATED"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class CandidateGateResult:
    gate_version: str
    status: str
    publication_allowed: bool
    database_status: str
    database_present: bool
    database_size_bytes: int | None
    items_count: int | None
    item_snapshots_count: int | None
    collection_runs_count: int | None
    artifact_validation: str
    candidate_item_count: int | None
    candidate_shard_count: int
    rights_gate: str
    lifecycle_gate: str
    semantics_gate: str
    publication_status_gate: str
    data_policy_gate: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(audit: Any, **changes: Any) -> CandidateGateResult:
    values = {
        "gate_version": GATE_VERSION,
        "status": BLOCKED,
        "publication_allowed": False,
        "database_status": audit.status,
        "database_present": audit.database_present,
        "database_size_bytes": audit.database_size_bytes,
        "items_count": audit.items_count,
        "item_snapshots_count": audit.item_snapshots_count,
        "collection_runs_count": audit.collection_runs_count,
        "artifact_validation": "NOT_RUN",
        "candidate_item_count": None,
        "candidate_shard_count": 0,
        "rights_gate": "NOT_RUN",
        "lifecycle_gate": "NOT_RUN",
        "semantics_gate": "NOT_RUN",
        "publication_status_gate": "NOT_RUN",
        "data_policy_gate": "NOT_RUN",
        "reason_codes": tuple(audit.reason_codes),
    }
    values.update(changes)
    return CandidateGateResult(**values)


def _load_builder() -> Any:
    path = ROOT / "scripts" / "build-public-data.py"
    specification = importlib.util.spec_from_file_location(
        "revenue_mvp_public_data_builder", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("builder unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def run_gate(
    database_path: Path,
    *,
    as_of: datetime,
    generated_at: datetime,
    build_documents: Callable[[Path, datetime, datetime], tuple[dict[str, bytes], dict[str, Any]]] | None = None,
) -> CandidateGateResult:
    """Validate in memory only; never write candidate artifacts or production data."""

    audit = audit_database(database_path)
    if audit.status != DATABASE_READY:
        return _result(audit)
    try:
        builder = _load_builder() if build_documents is None else None
        build = build_documents or builder.build_documents
        files, _ = build(database_path, as_of, generated_at)
        artifact = validate_artifacts(files)
        publication = evaluate_publication_gate(files)
        reasons = set(artifact.reason_codes) | set(publication.reason_codes)
        if artifact.artifact_validation != "PASS":
            reasons.add("ARTIFACT_VALIDATION_FAILED")
        status = (
            LOCAL_CANDIDATE_VALIDATED
            if artifact.artifact_validation == "PASS"
            else BLOCKED
        )
        return _result(
            audit,
            status=status,
            artifact_validation=artifact.artifact_validation,
            candidate_item_count=artifact.item_count,
            candidate_shard_count=artifact.shard_count,
            rights_gate=publication.rights_gate,
            lifecycle_gate=publication.lifecycle_gate,
            semantics_gate=publication.semantics_gate,
            publication_status_gate=publication.publication_status_gate,
            data_policy_gate=publication.data_policy_gate,
            reason_codes=tuple(sorted(reasons)) or ("LOCAL_CANDIDATE_VALIDATED",),
        )
    except Exception:
        return _result(audit, status=FAIL_CLOSED, reason_codes=("CANDIDATE_BUILD_FAILED",))


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Revenue MVP data candidate without publishing it."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--as-of", type=_timestamp)
    parser.add_argument("--generated-at", type=_timestamp)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    result = run_gate(
        args.db,
        as_of=args.as_of or now,
        generated_at=args.generated_at or now,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == LOCAL_CANDIDATE_VALIDATED else 2


if __name__ == "__main__":
    raise SystemExit(main())
