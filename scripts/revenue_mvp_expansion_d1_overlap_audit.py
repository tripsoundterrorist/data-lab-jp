"""Read-only aggregate overlap audit between a D1 snapshot and 300-item candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import sqlite3
from typing import Any

import affiliate_d1_incremental_reconciliation as reconciliation
from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VERSION = "0.1"
AUDITED = "OVERLAP_AUDITED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class OverlapAudit:
    version: str
    status: str
    remote_row_count: int
    candidate_row_count: int
    exact_mapping_match_count: int
    candidate_missing_count: int
    mapping_conflict_count: int
    candidate_eligible_count: int
    candidate_redirect_count: int
    candidate_runtime_redirect_count: int
    candidate_ids_exposed: bool
    production_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> OverlapAudit:
    return OverlapAudit(
        VERSION, BLOCKED, 0, 0, 0, 0, 0, 0, 0, 0,
        False, False, False, (reason,),
    )


def assess(
    remote: Path,
    candidate: Path,
    *,
    expected_remote_sha256: Any,
    expected_candidate_sha256: Any,
) -> OverlapAudit:
    connection: sqlite3.Connection | None = None
    try:
        remote_bytes = _snapshot_regular_file(remote)
        candidate_bytes = _snapshot_regular_file(candidate)
        schema_bytes = _snapshot_regular_file(SCHEMA)
        if (
            type(expected_remote_sha256) is not str
            or type(expected_candidate_sha256) is not str
            or hashlib.sha256(remote_bytes).hexdigest() != expected_remote_sha256
            or hashlib.sha256(candidate_bytes).hexdigest() != expected_candidate_sha256
        ):
            return _blocked("IDENTITY_MISMATCH")
        candidate_rows = reconciliation._parse_candidate(candidate_bytes)
        if len(candidate_rows) != 300:
            return _blocked("CANDIDATE_COUNT_INVALID")
        candidate_set = set(candidate_rows)
        if len(candidate_set) != 300:
            return _blocked("CANDIDATE_MAPPING_NOT_UNIQUE")

        connection = sqlite3.connect(":memory:")
        connection.executescript(schema_bytes.decode("utf-8"))
        connection.executescript(remote_bytes.decode("utf-8"))
        remote_rows = set(connection.execute(
            "SELECT public_id,content_id FROM affiliate_item_lookup"
        ))
        remote_by_public = dict(remote_rows)
        remote_by_content = {content_id: public_id for public_id, content_id in remote_rows}
        matches = len(remote_rows & candidate_set)
        missing = 0
        conflicts = 0
        for public_id, content_id in candidate_rows:
            if (public_id, content_id) in remote_rows:
                continue
            if public_id in remote_by_public or content_id in remote_by_content:
                conflicts += 1
            else:
                missing += 1
        placeholders = ",".join("?" for _ in candidate_rows)
        public_ids = tuple(public_id for public_id, _ in candidate_rows)
        eligible = connection.execute(
            f"SELECT count(*) FROM affiliate_runtime_eligible_lookup WHERE public_id IN ({placeholders})",
            public_ids,
        ).fetchone()[0]
        redirects = connection.execute(
            f"SELECT count(*) FROM affiliate_redirect_target WHERE public_id IN ({placeholders})",
            public_ids,
        ).fetchone()[0]
        runtime_redirects = connection.execute(
            f"SELECT count(*) FROM affiliate_runtime_redirect_target WHERE public_id IN ({placeholders})",
            public_ids,
        ).fetchone()[0]
        reasons = ["READ_ONLY_AGGREGATE_AUDIT", "D1_WRITE_NOT_AUTHORIZED"]
        if conflicts:
            reasons.append("MAPPING_CONFLICT_DETECTED")
        if missing:
            reasons.append("CANDIDATE_ROWS_MISSING")
        if runtime_redirects != 300:
            reasons.append("RUNTIME_COVERAGE_INCOMPLETE")
        return OverlapAudit(
            VERSION, AUDITED, len(remote_rows), 300, matches, missing, conflicts,
            eligible, redirects, runtime_redirects, False, False, False,
            tuple(reasons),
        )
    except (OSError, UnicodeError, sqlite3.Error, ValueError):
        return _blocked("OVERLAP_AUDIT_FAILED")
    finally:
        if connection is not None:
            connection.close()


__all__ = ["OverlapAudit", "assess"]
