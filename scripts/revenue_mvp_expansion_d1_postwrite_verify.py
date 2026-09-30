"""Verify the scoped expansion D1 write from immutable before/after exports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import sqlite3
from typing import Any

import affiliate_d1_incremental_reconciliation as reconciliation
import revenue_mvp_expansion_d1_delta as delta_builder
from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VERSION = "0.1"
VERIFIED = "POSTWRITE_VERIFIED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PostwriteVerification:
    version: str
    status: str
    before_row_count: int
    after_row_count: int
    new_row_count: int
    existing_rows_unchanged: bool
    new_mapping_exact_candidate_gap: bool
    new_rows_disabled_and_pending: bool
    eligibility_unchanged: bool
    redirect_targets_unchanged: bool
    runtime_redirects_unchanged: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> PostwriteVerification:
    return PostwriteVerification(
        VERSION, BLOCKED, 0, 0, 0, False, False, False,
        False, False, False, False, (reason,),
    )


def verify(
    before_bytes: bytes,
    after_bytes: bytes,
    candidate_bytes: bytes,
    schema_bytes: bytes,
    *,
    expected_before_sha256: Any,
    expected_after_sha256: Any,
    expected_candidate_sha256: Any,
    expected_before_row_count: Any = 1109,
    expected_after_row_count: Any = 1287,
    expected_new_row_count: Any = 178,
) -> PostwriteVerification:
    connections: list[sqlite3.Connection] = []
    try:
        actual = (
            hashlib.sha256(before_bytes).hexdigest(),
            hashlib.sha256(after_bytes).hexdigest(),
            hashlib.sha256(candidate_bytes).hexdigest(),
        )
        expected = (
            expected_before_sha256, expected_after_sha256, expected_candidate_sha256,
        )
        if any(type(value) is not str for value in expected) or actual != expected:
            return _blocked("IDENTITY_MISMATCH")
        expected_counts = (
            expected_before_row_count, expected_after_row_count, expected_new_row_count,
        )
        if any(type(value) is not int or value < 0 for value in expected_counts):
            return _blocked("EXPECTED_COUNTS_INVALID")
        candidate = set(reconciliation._parse_candidate(candidate_bytes))
        if len(candidate) != 300:
            return _blocked("CANDIDATE_COUNT_INVALID")
        states: list[dict[str, Any]] = []
        for payload in (before_bytes, after_bytes):
            connection = sqlite3.connect(":memory:")
            connections.append(connection)
            delta_builder.load_remote_snapshot(connection, schema_bytes, payload)
            rows = connection.execute(
                """SELECT public_id,content_id,rights_status,lifecycle_status,
                          verification_status,affiliate_enabled,updated_at
                   FROM affiliate_item_lookup ORDER BY public_id"""
            ).fetchall()
            states.append({
                "rows": {row[0]: row for row in rows},
                "eligible": connection.execute(
                    "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
                ).fetchone()[0],
                "redirects": connection.execute(
                    "SELECT count(*) FROM affiliate_redirect_target"
                ).fetchone()[0],
                "runtime": connection.execute(
                    "SELECT count(*) FROM affiliate_runtime_redirect_target"
                ).fetchone()[0],
            })
        before = states[0]["rows"]
        after = states[1]["rows"]
        new_rows = [row for public_id, row in after.items() if public_id not in before]
        existing_unchanged = all(after.get(public_id) == row for public_id, row in before.items())
        before_mappings = {(row[0], row[1]) for row in before.values()}
        new_mappings = {(row[0], row[1]) for row in new_rows}
        exact_gap = new_mappings == candidate - before_mappings
        new_safe = all(
            row[2:] == (
                "PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION",
                "PENDING", 0, "1970-01-01T00:00:00Z",
            )
            for row in new_rows
        )
        eligibility_unchanged = states[0]["eligible"] == states[1]["eligible"]
        redirects_unchanged = states[0]["redirects"] == states[1]["redirects"]
        runtime_unchanged = states[0]["runtime"] == states[1]["runtime"]
        valid = (
            len(before) == expected_before_row_count
            and len(after) == expected_after_row_count
            and len(new_rows) == expected_new_row_count
            and existing_unchanged and exact_gap and new_safe
            and eligibility_unchanged and redirects_unchanged and runtime_unchanged
        )
        if not valid:
            return _blocked("POSTWRITE_INVARIANT_FAILED")
        return PostwriteVerification(
            VERSION, VERIFIED, len(before), len(after), len(new_rows), True, True, True,
            True, True, True, False,
            (
                "EXISTING_ROWS_PRESERVED", "EXACT_CANDIDATE_GAP_INSERTED",
                "NEW_ROWS_DISABLED_AND_PENDING", "PUBLICATION_NOT_AUTHORIZED",
            ),
        )
    except Exception:
        return _blocked("POSTWRITE_VERIFICATION_FAILED")
    finally:
        for connection in connections:
            connection.close()


def verify_files(before: Path, after: Path, candidate: Path, **kwargs: Any) -> PostwriteVerification:
    try:
        if any(path.is_symlink() for path in (before, after, candidate, SCHEMA)):
            return _blocked("SYMLINK_PATH_REJECTED")
        return verify(
            _snapshot_regular_file(before), _snapshot_regular_file(after),
            _snapshot_regular_file(candidate), _snapshot_regular_file(SCHEMA), **kwargs,
        )
    except Exception:
        return _blocked("FILE_OPERATION_FAILED")


__all__ = ["PostwriteVerification", "verify", "verify_files"]
