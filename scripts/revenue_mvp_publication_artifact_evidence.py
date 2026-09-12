"""Verify the sanitized publication-artifact receipt against the current DB."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
EVIDENCE_READY = "ARTIFACT_VALIDATION_EVIDENCE_READY"
BLOCKED = "ARTIFACT_VALIDATION_EVIDENCE_BLOCKED"
RECEIPT = ROOT / "runtime" / "evidence" / "revenue-mvp-publication-artifact-validation-20260912.json"
DB = ROOT / "data" / "data-lab.db"


@dataclass(frozen=True)
class PublicationArtifactEvidence:
    version: str
    status: str
    source_db_matches: bool
    artifact_validation_passed: bool
    item_count: int | None
    publication_allowed: bool
    production_write_performed: bool
    gate_unlock_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_evidence() -> PublicationArtifactEvidence:
    try:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        digest = hashlib.sha256(DB.read_bytes()).hexdigest()
        exact_keys = {
            "evidence_version", "validated_on", "source_db_relative_path",
            "source_db_sha256", "public_schema_version", "public_policy_version",
            "validator_version", "artifact_validation", "item_count", "shard_count",
            "index_sha256", "detail_aggregate_sha256", "publication_allowed",
            "production_write_performed", "gate_unlock_allowed",
        }
        valid = (
            isinstance(receipt, dict)
            and set(receipt) == exact_keys
            and receipt["evidence_version"] == VERSION
            and receipt["source_db_relative_path"] == "data/data-lab.db"
            and receipt["source_db_sha256"] == digest
            and receipt["public_schema_version"] == "0.1"
            and receipt["public_policy_version"] == "0.1"
            and receipt["validator_version"] == "0.1"
            and receipt["artifact_validation"] == "PASS"
            and type(receipt["item_count"]) is int
            and receipt["item_count"] > 0
            and receipt["shard_count"] == receipt["item_count"]
            and receipt["publication_allowed"] is False
            and receipt["production_write_performed"] is False
            and receipt["gate_unlock_allowed"] is False
        )
        if not valid:
            raise ValueError("receipt mismatch")
        return PublicationArtifactEvidence(
            VERSION, EVIDENCE_READY, True, True, receipt["item_count"],
            False, False, False,
            ("CURRENT_DB_ARTIFACT_VALIDATED", "PUBLICATION_GATE_REMAINS_CLOSED"),
        )
    except Exception:
        return PublicationArtifactEvidence(
            VERSION, BLOCKED, False, False, None, False, False, False,
            ("ARTIFACT_RECEIPT_OR_SOURCE_MISMATCH",),
        )


def main() -> int:
    result = assess_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == EVIDENCE_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
