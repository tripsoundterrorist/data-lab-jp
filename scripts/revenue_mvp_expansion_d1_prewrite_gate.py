"""Fail-closed final gate for the scoped expansion D1 delta."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

import revenue_mvp_expansion_d1_delta as delta_builder
from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VERSION = "0.1"
READY = "PREWRITE_REVIEW_READY"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PrewriteGate:
    version: str
    status: str
    export_fresh: bool
    remote_identity_verified: bool
    candidate_identity_verified: bool
    delta_identity_verified: bool
    exact_delta_verified: bool
    remote_row_count: int
    delta_row_count: int
    final_row_count: int
    production_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> PrewriteGate:
    return PrewriteGate(
        VERSION, BLOCKED, False, False, False, False, False,
        0, 0, 0, False, False, (reason,),
    )


def assess(
    remote_bytes: bytes,
    candidate_bytes: bytes,
    delta_bytes: bytes,
    schema_bytes: bytes,
    *,
    expected_remote_sha256: Any,
    expected_candidate_sha256: Any,
    expected_delta_sha256: Any,
    exported_at: Any,
    evaluated_at: Any,
    maximum_age_seconds: Any = 900,
    expected_remote_row_count: Any = 1109,
    expected_delta_row_count: Any = 178,
    expected_final_row_count: Any = 1287,
) -> PrewriteGate:
    try:
        if not (
            isinstance(exported_at, datetime) and isinstance(evaluated_at, datetime)
            and exported_at.tzinfo is not None and evaluated_at.tzinfo is not None
            and type(maximum_age_seconds) is int and 0 < maximum_age_seconds <= 900
        ):
            return _blocked("FRESHNESS_INPUT_INVALID")
        age = (evaluated_at.astimezone(timezone.utc) - exported_at.astimezone(timezone.utc)).total_seconds()
        if age < 0 or age > maximum_age_seconds:
            return _blocked("REMOTE_EXPORT_STALE")
        hashes = (
            hashlib.sha256(remote_bytes).hexdigest(),
            hashlib.sha256(candidate_bytes).hexdigest(),
            hashlib.sha256(delta_bytes).hexdigest(),
        )
        expected = (expected_remote_sha256, expected_candidate_sha256, expected_delta_sha256)
        if any(type(value) is not str for value in expected) or hashes != expected:
            return _blocked("ARTIFACT_IDENTITY_MISMATCH")
        receipt, exact_delta = delta_builder.build(
            remote_bytes, candidate_bytes, schema_bytes,
            expected_remote_sha256=expected_remote_sha256,
            expected_candidate_sha256=expected_candidate_sha256,
        )
        if receipt.status != delta_builder.READY or exact_delta != delta_bytes:
            return _blocked("DELTA_NO_LONGER_EXACT")
        count_values = (
            expected_remote_row_count, expected_delta_row_count, expected_final_row_count,
        )
        if any(type(value) is not int or value < 0 for value in count_values):
            return _blocked("EXPECTED_COUNTS_INVALID")
        if (
            receipt.remote_row_count != expected_remote_row_count
            or receipt.delta_row_count != expected_delta_row_count
            or receipt.final_row_count != expected_final_row_count
            or not receipt.existing_rows_unchanged
            or not receipt.new_rows_disabled_and_pending
            or not receipt.runtime_eligibility_unchanged
        ):
            return _blocked("PREWRITE_POSTCONDITION_MISMATCH")
        return PrewriteGate(
            VERSION, READY, True, True, True, True, True,
            receipt.remote_row_count, receipt.delta_row_count, receipt.final_row_count,
            False, False,
            (
                "FRESH_REMOTE_EXPORT_VERIFIED", "EXACT_DISABLED_DELTA_VERIFIED",
                "SEPARATE_D1_WRITE_APPROVAL_REQUIRED",
            ),
        )
    except Exception:
        return _blocked("PREWRITE_GATE_FAILED")


def assess_files(remote: Path, candidate: Path, delta: Path, **kwargs: Any) -> PrewriteGate:
    try:
        if any(path.is_symlink() for path in (remote, candidate, delta, SCHEMA)):
            return _blocked("SYMLINK_PATH_REJECTED")
        return assess(
            _snapshot_regular_file(remote), _snapshot_regular_file(candidate),
            _snapshot_regular_file(delta), _snapshot_regular_file(SCHEMA), **kwargs,
        )
    except Exception:
        return _blocked("FILE_OPERATION_FAILED")


__all__ = ["PrewriteGate", "assess", "assess_files"]
