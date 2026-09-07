"""Validate one private, disabled-only affiliate lookup SQL candidate."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "runtime" / "private" / "affiliate-item-lookup.sql"
DEFAULT_SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VALIDATION_VERSION = "0.2"
VALIDATED = "VALIDATED"
FAIL_CLOSED = "FAIL_CLOSED"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
INSERT_PATTERN = re.compile(
    r"INSERT INTO affiliate_item_lookup "
    r"\(public_id, content_id, updated_at\) VALUES "
    r"\('(itm_[0-9a-f]{24})', '([A-Za-z0-9._-]{1,128})', '1970-01-01T00:00:00Z'\);\Z"
)


@dataclass(frozen=True)
class ValidationResult:
    validation_version: str
    status: str
    row_count: int
    all_rows_disabled: bool
    pending_defaults_verified: bool
    eligible_row_count: int
    candidate_identity_verified: bool
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
    all_disabled: bool = False,
    defaults_verified: bool = False,
    eligible_count: int = 0,
    identity_verified: bool = False,
) -> ValidationResult:
    return ValidationResult(
        VALIDATION_VERSION,
        status,
        row_count,
        all_disabled,
        defaults_verified,
        eligible_count,
        identity_verified,
        reasons,
    )


def _snapshot_regular_file(path: Path) -> bytes:
    """Read one stable regular-file snapshot while rejecting direct symlink inputs."""

    if path.is_symlink():
        raise OSError("symlink input rejected")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise OSError("regular file required")
    before = resolved.stat()
    data = resolved.read_bytes()
    after = resolved.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or len(data) != after.st_size:
        raise OSError("file changed while snapshotting")
    return data


def validate_candidate_snapshot(
    candidate_bytes: bytes,
    schema_bytes: bytes,
    *,
    expected_sha256: Any,
    expected_row_count: Any,
) -> ValidationResult:
    """Validate exact candidate/schema snapshots without reopening filesystem inputs."""

    try:
        if not isinstance(expected_sha256, str) or SHA256_PATTERN.fullmatch(expected_sha256) is None:
            return _result(FAIL_CLOSED, ("EXPECTED_SHA256_REQUIRED",))
        if not isinstance(expected_row_count, int) or isinstance(expected_row_count, bool) or expected_row_count <= 0:
            return _result(FAIL_CLOSED, ("EXPECTED_ROW_COUNT_REQUIRED",))
        if hashlib.sha256(candidate_bytes).hexdigest() != expected_sha256:
            return _result(FAIL_CLOSED, ("CANDIDATE_IDENTITY_MISMATCH",))

        candidate_text = candidate_bytes.decode("utf-8")
        schema_text = schema_bytes.decode("utf-8")
        lines = candidate_text.splitlines()
        if len(lines) != expected_row_count + 2:
            return _result(FAIL_CLOSED, ("CANDIDATE_STATEMENT_COUNT_MISMATCH",), identity_verified=True)
        if lines[0] != "BEGIN TRANSACTION;" or lines[-1] != "COMMIT;":
            return _result(FAIL_CLOSED, ("CANDIDATE_TRANSACTION_BOUNDARY_INVALID",), identity_verified=True)

        public_ids: set[str] = set()
        content_ids: set[str] = set()
        for line in lines[1:-1]:
            match = INSERT_PATTERN.fullmatch(line)
            if match is None:
                return _result(FAIL_CLOSED, ("CANDIDATE_STATEMENT_INVALID",), identity_verified=True)
            public_id, content_id = match.groups()
            if public_id in public_ids or content_id in content_ids:
                return _result(FAIL_CLOSED, ("CANDIDATE_IDENTIFIER_NOT_UNIQUE",), identity_verified=True)
            public_ids.add(public_id)
            content_ids.add(content_id)

        if len(public_ids) != expected_row_count:
            return _result(FAIL_CLOSED, ("CANDIDATE_ROW_COUNT_MISMATCH",), identity_verified=True)

        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(schema_text)
            connection.executescript(candidate_text)
            row_count = connection.execute("SELECT COUNT(*) FROM affiliate_item_lookup").fetchone()[0]
            disabled_count = connection.execute(
                "SELECT COUNT(*) FROM affiliate_item_lookup WHERE affiliate_enabled = 0"
            ).fetchone()[0]
            pending_count = connection.execute(
                "SELECT COUNT(*) FROM affiliate_item_lookup "
                "WHERE rights_status = 'PENDING_SEPARATE_POLICY' "
                "AND lifecycle_status = 'PENDING_OFFICIAL_CONFIRMATION' "
                "AND verification_status = 'PENDING'"
            ).fetchone()[0]
            eligible_count = connection.execute(
                "SELECT COUNT(*) FROM affiliate_runtime_eligible_lookup"
            ).fetchone()[0]
        finally:
            connection.close()

        if row_count != expected_row_count:
            return _result(FAIL_CLOSED, ("IMPORTED_ROW_COUNT_MISMATCH",), row_count=row_count, identity_verified=True)
        if disabled_count != row_count:
            return _result(FAIL_CLOSED, ("AFFILIATE_ROW_ENABLED",), row_count=row_count, identity_verified=True)
        if pending_count != row_count:
            return _result(FAIL_CLOSED, ("PENDING_DEFAULTS_NOT_PRESERVED",), row_count=row_count, all_disabled=True, identity_verified=True)
        if eligible_count != 0:
            return _result(FAIL_CLOSED, ("RUNTIME_ELIGIBILITY_NOT_EMPTY",), row_count=row_count, all_disabled=True, defaults_verified=True, eligible_count=eligible_count, identity_verified=True)

        return _result(
            VALIDATED,
            ("PRIVATE_DISABLED_LOOKUP_VALIDATED",),
            row_count=row_count,
            all_disabled=True,
            defaults_verified=True,
            eligible_count=0,
            identity_verified=True,
        )
    except (UnicodeError, sqlite3.Error):
        return _result(FAIL_CLOSED, ("VALIDATION_OPERATION_FAILED",))
    except Exception:
        return _result(FAIL_CLOSED, ("VALIDATION_INTERNAL_ERROR",))


def validate_candidate(
    candidate_path: Path,
    schema_path: Path,
    *,
    expected_sha256: Any,
    expected_row_count: Any,
) -> ValidationResult:
    """Validate shape, identity, schema defaults, and zero runtime eligibility in memory."""

    try:
        if candidate_path.is_symlink():
            return _result(FAIL_CLOSED, ("CANDIDATE_SYMLINK_REJECTED",))
        if schema_path.is_symlink():
            return _result(FAIL_CLOSED, ("SCHEMA_SYMLINK_REJECTED",))
        candidate_bytes = _snapshot_regular_file(candidate_path)
        schema_bytes = _snapshot_regular_file(schema_path)
    except (OSError, RuntimeError):
        if not candidate_path.exists():
            return _result(FAIL_CLOSED, ("CANDIDATE_UNAVAILABLE",))
        if not schema_path.exists():
            return _result(FAIL_CLOSED, ("SCHEMA_UNAVAILABLE",))
        return _result(FAIL_CLOSED, ("SNAPSHOT_UNSTABLE",))
    except Exception:
        return _result(FAIL_CLOSED, ("VALIDATION_INTERNAL_ERROR",))

    return validate_candidate_snapshot(
        candidate_bytes,
        schema_bytes,
        expected_sha256=expected_sha256,
        expected_row_count=expected_row_count,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the private affiliate lookup SQL candidate.")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-row-count", type=int, required=True)
    args = parser.parse_args(argv)
    result = validate_candidate(
        args.candidate,
        args.schema,
        expected_sha256=args.expected_sha256,
        expected_row_count=args.expected_row_count,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == VALIDATED else 2


__all__ = [
    "FAIL_CLOSED",
    "VALIDATED",
    "VALIDATION_VERSION",
    "ValidationResult",
    "validate_candidate",
    "validate_candidate_snapshot",
]


if __name__ == "__main__":
    raise SystemExit(main())
