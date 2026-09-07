"""Fail-closed preflight for a future manual Cloudflare D1 import."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from validate_affiliate_item_lookup_candidate import (
    FAIL_CLOSED as VALIDATION_FAIL_CLOSED,
    VALIDATED,
    _snapshot_regular_file,
    validate_candidate_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "runtime" / "private" / "affiliate-item-lookup.sql"
DEFAULT_SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
PREFLIGHT_VERSION = "0.2"
PREFLIGHT_READY = "PREFLIGHT_READY"
FAIL_CLOSED = "FAIL_CLOSED"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class D1ImportPreflightResult:
    preflight_version: str
    status: str
    row_count: int
    schema_identity_verified: bool
    candidate_identity_verified: bool
    all_rows_disabled: bool
    pending_defaults_verified: bool
    eligible_row_count: int
    d1_import_allowed: bool
    cloudflare_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    reasons: tuple[str, ...],
    *,
    row_count: int = 0,
    schema_identity_verified: bool = False,
    candidate_identity_verified: bool = False,
    all_rows_disabled: bool = False,
    pending_defaults_verified: bool = False,
    eligible_row_count: int = 0,
) -> D1ImportPreflightResult:
    return D1ImportPreflightResult(
        PREFLIGHT_VERSION,
        status,
        row_count,
        schema_identity_verified,
        candidate_identity_verified,
        all_rows_disabled,
        pending_defaults_verified,
        eligible_row_count,
        False,
        False,
        reasons,
    )


def preflight_d1_import(
    candidate_path: Path,
    schema_path: Path,
    *,
    expected_candidate_sha256: Any,
    expected_schema_sha256: Any,
    expected_row_count: Any,
) -> D1ImportPreflightResult:
    """Validate immutable import-input snapshots without creating or writing a D1 resource."""

    try:
        if candidate_path.is_symlink():
            return _result(FAIL_CLOSED, ("CANDIDATE_SYMLINK_REJECTED",))
        if schema_path.is_symlink():
            return _result(FAIL_CLOSED, ("SCHEMA_SYMLINK_REJECTED",))
        if (
            not isinstance(expected_candidate_sha256, str)
            or SHA256_PATTERN.fullmatch(expected_candidate_sha256) is None
        ):
            return _result(FAIL_CLOSED, ("EXPECTED_CANDIDATE_SHA256_REQUIRED",))
        if (
            not isinstance(expected_schema_sha256, str)
            or SHA256_PATTERN.fullmatch(expected_schema_sha256) is None
        ):
            return _result(FAIL_CLOSED, ("EXPECTED_SCHEMA_SHA256_REQUIRED",))
        if (
            not isinstance(expected_row_count, int)
            or isinstance(expected_row_count, bool)
            or expected_row_count <= 0
        ):
            return _result(FAIL_CLOSED, ("EXPECTED_ROW_COUNT_REQUIRED",))

        candidate_bytes = _snapshot_regular_file(candidate_path)
        schema_bytes = _snapshot_regular_file(schema_path)
        if hashlib.sha256(schema_bytes).hexdigest() != expected_schema_sha256:
            return _result(FAIL_CLOSED, ("SCHEMA_IDENTITY_MISMATCH",))
        if hashlib.sha256(candidate_bytes).hexdigest() != expected_candidate_sha256:
            return _result(
                FAIL_CLOSED,
                ("CANDIDATE_IDENTITY_MISMATCH",),
                schema_identity_verified=True,
            )

        validation = validate_candidate_snapshot(
            candidate_bytes,
            schema_bytes,
            expected_sha256=expected_candidate_sha256,
            expected_row_count=expected_row_count,
        )
        if validation.status != VALIDATED:
            reason = (
                "PRIVATE_ARTIFACT_VALIDATION_FAILED"
                if validation.status == VALIDATION_FAIL_CLOSED
                else "PRIVATE_ARTIFACT_VALIDATION_UNKNOWN"
            )
            return _result(
                FAIL_CLOSED,
                (reason,),
                row_count=validation.row_count,
                schema_identity_verified=True,
                candidate_identity_verified=validation.candidate_identity_verified,
                all_rows_disabled=validation.all_rows_disabled,
                pending_defaults_verified=validation.pending_defaults_verified,
                eligible_row_count=validation.eligible_row_count,
            )

        if not validation.candidate_identity_verified:
            return _result(
                FAIL_CLOSED,
                ("CANDIDATE_IDENTITY_NOT_VERIFIED",),
                row_count=validation.row_count,
                schema_identity_verified=True,
            )
        if not validation.all_rows_disabled:
            return _result(
                FAIL_CLOSED,
                ("AFFILIATE_ROWS_NOT_DISABLED",),
                row_count=validation.row_count,
                schema_identity_verified=True,
                candidate_identity_verified=True,
            )
        if not validation.pending_defaults_verified:
            return _result(
                FAIL_CLOSED,
                ("PENDING_DEFAULTS_NOT_VERIFIED",),
                row_count=validation.row_count,
                schema_identity_verified=True,
                candidate_identity_verified=True,
                all_rows_disabled=True,
            )
        if validation.eligible_row_count != 0:
            return _result(
                FAIL_CLOSED,
                ("RUNTIME_ELIGIBILITY_NOT_EMPTY",),
                row_count=validation.row_count,
                schema_identity_verified=True,
                candidate_identity_verified=True,
                all_rows_disabled=True,
                pending_defaults_verified=True,
                eligible_row_count=validation.eligible_row_count,
            )

        return _result(
            PREFLIGHT_READY,
            ("PRIVATE_D1_IMPORT_INPUTS_READY", "MANUAL_CLOUDFLARE_STEP_REQUIRED"),
            row_count=validation.row_count,
            schema_identity_verified=True,
            candidate_identity_verified=True,
            all_rows_disabled=True,
            pending_defaults_verified=True,
            eligible_row_count=0,
        )
    except FileNotFoundError:
        if not candidate_path.exists():
            return _result(FAIL_CLOSED, ("CANDIDATE_UNAVAILABLE",))
        return _result(FAIL_CLOSED, ("SCHEMA_UNAVAILABLE",))
    except (OSError, RuntimeError):
        return _result(FAIL_CLOSED, ("SNAPSHOT_UNSTABLE",))
    except Exception:
        return _result(FAIL_CLOSED, ("PREFLIGHT_INTERNAL_ERROR",))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify private affiliate lookup artifacts before any manual D1 import."
    )
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--expected-schema-sha256", required=True)
    parser.add_argument("--expected-row-count", type=int, required=True)
    args = parser.parse_args(argv)
    result = preflight_d1_import(
        args.candidate,
        args.schema,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_schema_sha256=args.expected_schema_sha256,
        expected_row_count=args.expected_row_count,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PREFLIGHT_READY else 2


__all__ = [
    "D1ImportPreflightResult",
    "FAIL_CLOSED",
    "PREFLIGHT_READY",
    "PREFLIGHT_VERSION",
    "preflight_d1_import",
]


if __name__ == "__main__":
    raise SystemExit(main())
