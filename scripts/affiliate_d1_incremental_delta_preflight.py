"""Validate and apply an insert-only D1 delta in isolated in-memory SQLite."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import affiliate_d1_incremental_reconciliation as reconciliation
from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
READY = "DELTA_PREFLIGHT_READY"
FAIL_CLOSED = "FAIL_CLOSED"
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"


@dataclass(frozen=True)
class IncrementalDeltaPreflight:
    version: str
    status: str
    remote_row_count: int
    candidate_row_count: int
    delta_row_count: int
    final_row_count: int
    all_rows_disabled: bool
    all_rows_pending: bool
    runtime_eligibility_empty: bool
    exact_delta_verified: bool
    isolated_memory_apply_verified: bool
    production_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(value["reason_codes"])
        return value


def _failed(reason: str) -> IncrementalDeltaPreflight:
    return IncrementalDeltaPreflight(
        VERSION, FAIL_CLOSED, 0, 0, 0, 0, False, False, False, False,
        False, False, False, (reason,),
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
    expected_remote_row_count: Any,
    expected_candidate_row_count: Any,
) -> IncrementalDeltaPreflight:
    """Verify exact derived delta then simulate it without persistent writes."""
    connection: sqlite3.Connection | None = None
    try:
        if (
            not isinstance(expected_delta_sha256, str)
            or reconciliation.SHA256_PATTERN.fullmatch(expected_delta_sha256) is None
            or hashlib.sha256(delta_bytes).hexdigest() != expected_delta_sha256
        ):
            return _failed("DELTA_IDENTITY_MISMATCH")
        result, expected_delta = reconciliation.reconcile_snapshots(
            remote_bytes,
            candidate_bytes,
            expected_remote_sha256=expected_remote_sha256,
            expected_candidate_sha256=expected_candidate_sha256,
            expected_remote_row_count=expected_remote_row_count,
            expected_candidate_row_count=expected_candidate_row_count,
        )
        if (
            result.status != reconciliation.READY
            or expected_delta is None
            or delta_bytes != expected_delta
        ):
            return _failed("DELTA_NOT_EXACT_RECONCILIATION_OUTPUT")
        delta_rows = result.missing_row_count
        connection = sqlite3.connect(":memory:")
        connection.executescript(schema_bytes.decode("utf-8"))
        connection.executescript(remote_bytes.decode("utf-8"))
        before = connection.execute(
            "SELECT count(*) FROM affiliate_item_lookup"
        ).fetchone()[0]
        connection.executescript(delta_bytes.decode("utf-8"))
        final = connection.execute(
            "SELECT count(*) FROM affiliate_item_lookup"
        ).fetchone()[0]
        enabled = connection.execute(
            "SELECT count(*) FROM affiliate_item_lookup WHERE affiliate_enabled != 0"
        ).fetchone()[0]
        nonpending = connection.execute(
            """SELECT count(*) FROM affiliate_item_lookup
               WHERE rights_status != 'PENDING_SEPARATE_POLICY'
                  OR lifecycle_status != 'PENDING_OFFICIAL_CONFIRMATION'
                  OR verification_status != 'PENDING'"""
        ).fetchone()[0]
        eligible = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        valid = (
            before == expected_remote_row_count
            and final == expected_candidate_row_count
            and final == before + delta_rows
            and enabled == 0
            and nonpending == 0
            and eligible == 0
        )
        if not valid:
            return _failed("ISOLATED_DELTA_POSTCONDITION_FAILED")
        return IncrementalDeltaPreflight(
            VERSION, READY, before, expected_candidate_row_count, delta_rows,
            final, True, True, True, True, True, False, False,
            (
                "EXACT_INSERT_ONLY_DELTA_VERIFIED",
                "ISOLATED_POSTCONDITIONS_VERIFIED",
                "SEPARATE_D1_WRITE_APPROVAL_REQUIRED",
            ),
        )
    except (UnicodeError, sqlite3.Error, ValueError, TypeError):
        return _failed("DELTA_PREFLIGHT_INPUT_INVALID")
    except Exception:
        return _failed("DELTA_PREFLIGHT_INTERNAL_ERROR")
    finally:
        if connection is not None:
            connection.close()


def assess_files(
    remote_path: Path,
    candidate_path: Path,
    delta_path: Path,
    **kwargs: Any,
) -> IncrementalDeltaPreflight:
    try:
        if any(path.is_symlink() for path in (remote_path, candidate_path, delta_path, SCHEMA)):
            return _failed("SYMLINK_PATH_REJECTED")
        return assess(
            _snapshot_regular_file(remote_path),
            _snapshot_regular_file(candidate_path),
            _snapshot_regular_file(delta_path),
            _snapshot_regular_file(SCHEMA),
            **kwargs,
        )
    except Exception:
        return _failed("DELTA_PREFLIGHT_FILE_OPERATION_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a D1 insert-only delta in isolated memory."
    )
    parser.add_argument("--remote-export", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--expected-remote-sha256", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--expected-delta-sha256", required=True)
    parser.add_argument("--expected-remote-row-count", type=int, required=True)
    parser.add_argument("--expected-candidate-row-count", type=int, required=True)
    args = parser.parse_args(argv)
    result = assess_files(
        args.remote_export, args.candidate, args.delta,
        expected_remote_sha256=args.expected_remote_sha256,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_delta_sha256=args.expected_delta_sha256,
        expected_remote_row_count=args.expected_remote_row_count,
        expected_candidate_row_count=args.expected_candidate_row_count,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
