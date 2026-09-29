"""Preflight an insert-only delta against an already active D1 snapshot."""

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
READY = "ACTIVE_DELTA_PREFLIGHT_READY"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class ActiveDeltaPreflight:
    version: str
    status: str
    remote_row_count: int
    delta_row_count: int
    final_row_count: int
    existing_rows_unchanged: bool
    new_rows_disabled_and_pending: bool
    runtime_eligibility_unchanged: bool
    exact_delta_verified: bool
    isolated_memory_apply_verified: bool
    production_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(reason: str) -> ActiveDeltaPreflight:
    return ActiveDeltaPreflight(
        VERSION, FAIL_CLOSED, 0, 0, 0, False, False, False, False,
        False, False, False, (reason,),
    )


def assess(
    remote_bytes: bytes,
    candidate_bytes: bytes,
    delta_bytes: bytes,
    schema_bytes: bytes,
    *,
    expected_remote_sha256: str,
    expected_candidate_sha256: str,
    expected_delta_sha256: str,
    expected_remote_row_count: int,
    expected_candidate_row_count: int,
) -> ActiveDeltaPreflight:
    connection: sqlite3.Connection | None = None
    try:
        if hashlib.sha256(delta_bytes).hexdigest() != expected_delta_sha256:
            return _failed("DELTA_IDENTITY_MISMATCH")
        result, exact_delta = reconciliation.reconcile_snapshots(
            remote_bytes, candidate_bytes,
            expected_remote_sha256=expected_remote_sha256,
            expected_candidate_sha256=expected_candidate_sha256,
            expected_remote_row_count=expected_remote_row_count,
            expected_candidate_row_count=expected_candidate_row_count,
        )
        if (
            result.status != reconciliation.READY
            or exact_delta is None or exact_delta != delta_bytes
        ):
            return _failed("DELTA_NOT_EXACT_RECONCILIATION_OUTPUT")

        connection = sqlite3.connect(":memory:")
        connection.executescript(schema_bytes.decode("utf-8"))
        connection.executescript(remote_bytes.decode("utf-8"))
        before = connection.execute("""
            SELECT public_id,content_id,rights_status,lifecycle_status,
                   verification_status,affiliate_enabled,updated_at
            FROM affiliate_item_lookup ORDER BY public_id
        """).fetchall()
        eligible_before = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        connection.executescript(delta_bytes.decode("utf-8"))
        after_existing = connection.execute("""
            SELECT public_id,content_id,rights_status,lifecycle_status,
                   verification_status,affiliate_enabled,updated_at
            FROM affiliate_item_lookup
            WHERE public_id IN ({}) ORDER BY public_id
        """.format(",".join("?" for _ in before)),
            tuple(row[0] for row in before),
        ).fetchall()
        final_count = connection.execute(
            "SELECT count(*) FROM affiliate_item_lookup"
        ).fetchone()[0]
        new_invalid = connection.execute("""
            SELECT count(*) FROM affiliate_item_lookup
            WHERE public_id NOT IN ({}) AND (
              rights_status != 'PENDING_SEPARATE_POLICY'
              OR lifecycle_status != 'PENDING_OFFICIAL_CONFIRMATION'
              OR verification_status != 'PENDING'
              OR affiliate_enabled != 0
              OR updated_at != '1970-01-01T00:00:00Z')
        """.format(",".join("?" for _ in before)),
            tuple(row[0] for row in before),
        ).fetchone()[0]
        eligible_after = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        valid = (
            len(before) == expected_remote_row_count
            and after_existing == before
            and final_count == expected_candidate_row_count
            and final_count == len(before) + result.missing_row_count
            and new_invalid == 0
            and eligible_after == eligible_before
        )
        if not valid:
            return _failed("ACTIVE_DELTA_POSTCONDITION_FAILED")
        return ActiveDeltaPreflight(
            VERSION, READY, len(before), result.missing_row_count, final_count,
            True, True, True, True, True, False, False,
            (
                "EXISTING_ACTIVE_ROWS_PRESERVED",
                "NEW_ROWS_DISABLED_AND_PENDING",
                "RUNTIME_ELIGIBILITY_UNCHANGED",
                "SEPARATE_D1_WRITE_APPROVAL_REQUIRED",
            ),
        )
    except (UnicodeError, sqlite3.Error, ValueError, TypeError):
        return _failed("ACTIVE_DELTA_PREFLIGHT_INPUT_INVALID")
    except Exception:
        return _failed("ACTIVE_DELTA_PREFLIGHT_INTERNAL_ERROR")
    finally:
        if connection is not None:
            connection.close()


def assess_files(remote: Path, candidate: Path, delta: Path, **kwargs: Any) -> ActiveDeltaPreflight:
    try:
        if any(path.is_symlink() for path in (remote, candidate, delta, SCHEMA)):
            return _failed("SYMLINK_PATH_REJECTED")
        return assess(
            _snapshot_regular_file(remote), _snapshot_regular_file(candidate),
            _snapshot_regular_file(delta), _snapshot_regular_file(SCHEMA), **kwargs,
        )
    except Exception:
        return _failed("ACTIVE_DELTA_PREFLIGHT_FILE_OPERATION_FAILED")

