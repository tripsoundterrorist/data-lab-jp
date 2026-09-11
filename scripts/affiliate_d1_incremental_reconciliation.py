"""Build a fail-closed, insert-only D1 reconciliation artifact."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from validate_affiliate_item_lookup_candidate import _snapshot_regular_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_EXPORT = (
    ROOT / "runtime" / "private" / "affiliate-item-lookup-remote-before-20260911.sql"
)
DEFAULT_CANDIDATE = ROOT / "runtime" / "private" / "affiliate-item-lookup.sql"
DEFAULT_DELTA = ROOT / "runtime" / "private" / "affiliate-item-lookup-delta.sql"
RECONCILIATION_VERSION = "0.1"
READY = "RECONCILIATION_READY"
SYNCHRONIZED = "ALREADY_SYNCHRONIZED"
FAIL_CLOSED = "FAIL_CLOSED"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
CANDIDATE_INSERT = re.compile(
    r"INSERT INTO affiliate_item_lookup "
    r"\(public_id, content_id, updated_at\) VALUES "
    r"\('(itm_[0-9a-f]{24})', '([A-Za-z0-9._-]{1,128})', "
    r"'1970-01-01T00:00:00Z'\);\Z"
)
REMOTE_INSERT = re.compile(
    r'INSERT INTO "affiliate_item_lookup" '
    r'\("public_id","content_id","rights_status","lifecycle_status",'
    r'"verification_status","affiliate_enabled","updated_at"\) VALUES'
    r"\('(itm_[0-9a-f]{24})','([A-Za-z0-9._-]{1,128})',"
    r"'PENDING_SEPARATE_POLICY','PENDING_OFFICIAL_CONFIRMATION','PENDING',0,"
    r"'1970-01-01T00:00:00Z'\);\Z"
)


@dataclass(frozen=True)
class ReconciliationResult:
    reconciliation_version: str
    status: str
    remote_row_count: int
    candidate_row_count: int
    missing_row_count: int
    remote_identity_verified: bool
    candidate_identity_verified: bool
    remote_subset_verified: bool
    all_remote_rows_disabled_and_pending: bool
    delta_written: bool
    delta_sha256: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, reasons: tuple[str, ...], **kwargs: Any) -> ReconciliationResult:
    defaults: dict[str, Any] = {
        "remote_row_count": 0,
        "candidate_row_count": 0,
        "missing_row_count": 0,
        "remote_identity_verified": False,
        "candidate_identity_verified": False,
        "remote_subset_verified": False,
        "all_remote_rows_disabled_and_pending": False,
        "delta_written": False,
        "delta_sha256": None,
    }
    defaults.update(kwargs)
    return ReconciliationResult(RECONCILIATION_VERSION, status, reason_codes=reasons, **defaults)


def _parse_candidate(data: bytes) -> list[tuple[str, str]]:
    lines = data.decode("utf-8").splitlines()
    if len(lines) < 3 or lines[0] != "BEGIN TRANSACTION;" or lines[-1] != "COMMIT;":
        raise ValueError("candidate boundary")
    rows: list[tuple[str, str]] = []
    for line in lines[1:-1]:
        match = CANDIDATE_INSERT.fullmatch(line)
        if match is None:
            raise ValueError("candidate statement")
        rows.append(match.groups())
    return rows


def _parse_remote(data: bytes) -> list[tuple[str, str]]:
    lines = data.decode("utf-8").splitlines()
    if not lines or lines[0] != "PRAGMA defer_foreign_keys=TRUE;":
        raise ValueError("remote boundary")
    rows: list[tuple[str, str]] = []
    for line in lines[1:]:
        match = REMOTE_INSERT.fullmatch(line)
        if match is None:
            raise ValueError("remote statement")
        rows.append(match.groups())
    return rows


def _unique_mapping(rows: list[tuple[str, str]]) -> bool:
    return len(rows) == len({public_id for public_id, _ in rows}) == len(
        {content_id for _, content_id in rows}
    )


def reconcile_snapshots(
    remote_bytes: bytes,
    candidate_bytes: bytes,
    *,
    expected_remote_sha256: Any,
    expected_candidate_sha256: Any,
    expected_remote_row_count: Any,
    expected_candidate_row_count: Any,
) -> tuple[ReconciliationResult, bytes | None]:
    """Compare immutable snapshots and return an insert-only delta in memory."""

    try:
        if not isinstance(expected_remote_sha256, str) or not SHA256_PATTERN.fullmatch(
            expected_remote_sha256
        ):
            return _result(FAIL_CLOSED, ("EXPECTED_REMOTE_SHA256_REQUIRED",)), None
        if not isinstance(expected_candidate_sha256, str) or not SHA256_PATTERN.fullmatch(
            expected_candidate_sha256
        ):
            return _result(FAIL_CLOSED, ("EXPECTED_CANDIDATE_SHA256_REQUIRED",)), None
        if hashlib.sha256(remote_bytes).hexdigest() != expected_remote_sha256:
            return _result(FAIL_CLOSED, ("REMOTE_IDENTITY_MISMATCH",)), None
        if hashlib.sha256(candidate_bytes).hexdigest() != expected_candidate_sha256:
            return _result(
                FAIL_CLOSED,
                ("CANDIDATE_IDENTITY_MISMATCH",),
                remote_identity_verified=True,
            ), None
        if (
            not isinstance(expected_remote_row_count, int)
            or isinstance(expected_remote_row_count, bool)
            or expected_remote_row_count < 0
            or not isinstance(expected_candidate_row_count, int)
            or isinstance(expected_candidate_row_count, bool)
            or expected_candidate_row_count <= 0
        ):
            return _result(FAIL_CLOSED, ("EXPECTED_ROW_COUNTS_INVALID",)), None

        remote_rows = _parse_remote(remote_bytes)
        candidate_rows = _parse_candidate(candidate_bytes)
        counts = {
            "remote_row_count": len(remote_rows),
            "candidate_row_count": len(candidate_rows),
            "remote_identity_verified": True,
            "candidate_identity_verified": True,
            "all_remote_rows_disabled_and_pending": True,
        }
        if len(remote_rows) != expected_remote_row_count or len(candidate_rows) != expected_candidate_row_count:
            return _result(FAIL_CLOSED, ("ROW_COUNT_MISMATCH",), **counts), None
        if not _unique_mapping(remote_rows) or not _unique_mapping(candidate_rows):
            return _result(FAIL_CLOSED, ("IDENTIFIER_NOT_UNIQUE",), **counts), None

        remote_set = set(remote_rows)
        candidate_set = set(candidate_rows)
        if not remote_set.issubset(candidate_set):
            return _result(FAIL_CLOSED, ("REMOTE_MAPPING_NOT_CANDIDATE_SUBSET",), **counts), None

        missing_rows = [row for row in candidate_rows if row not in remote_set]
        if not missing_rows:
            return _result(
                SYNCHRONIZED,
                ("REMOTE_EXACTLY_SYNCHRONIZED",),
                **counts,
                remote_subset_verified=True,
            ), None
        lines = ["INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES"]
        lines.extend(
            f"('{public_id}', '{content_id}', '1970-01-01T00:00:00Z')"
            + ("," if index < len(missing_rows) - 1 else ";")
            for index, (public_id, content_id) in enumerate(missing_rows)
        )
        delta_bytes = ("\n".join(lines) + "\n").encode("utf-8")
        return _result(
            READY,
            ("REMOTE_EXACT_SUBSET_VERIFIED", "INSERT_ONLY_DELTA_READY"),
            **counts,
            missing_row_count=len(missing_rows),
            remote_subset_verified=True,
            delta_sha256=hashlib.sha256(delta_bytes).hexdigest(),
        ), delta_bytes
    except (UnicodeError, ValueError):
        return _result(FAIL_CLOSED, ("INPUT_FORMAT_INVALID",)), None
    except Exception:
        return _result(FAIL_CLOSED, ("RECONCILIATION_INTERNAL_ERROR",)), None


def reconcile_files(
    remote_path: Path,
    candidate_path: Path,
    delta_path: Path,
    **kwargs: Any,
) -> ReconciliationResult:
    try:
        if remote_path.is_symlink() or candidate_path.is_symlink() or delta_path.is_symlink():
            return _result(FAIL_CLOSED, ("SYMLINK_PATH_REJECTED",))
        if delta_path.exists():
            return _result(FAIL_CLOSED, ("DELTA_ALREADY_EXISTS",))
        remote_bytes = _snapshot_regular_file(remote_path)
        candidate_bytes = _snapshot_regular_file(candidate_path)
        result, delta_bytes = reconcile_snapshots(remote_bytes, candidate_bytes, **kwargs)
        if result.status != READY or delta_bytes is None:
            return result
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        with delta_path.open("xb") as handle:
            handle.write(delta_bytes)
        return ReconciliationResult(**{**asdict(result), "delta_written": True})
    except FileExistsError:
        return _result(FAIL_CLOSED, ("DELTA_ALREADY_EXISTS",))
    except (OSError, RuntimeError):
        return _result(FAIL_CLOSED, ("FILESYSTEM_OPERATION_FAILED",))
    except Exception:
        return _result(FAIL_CLOSED, ("RECONCILIATION_INTERNAL_ERROR",))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a fail-closed D1 insert-only delta.")
    parser.add_argument("--remote-export", type=Path, default=DEFAULT_REMOTE_EXPORT)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--delta", type=Path, default=DEFAULT_DELTA)
    parser.add_argument("--expected-remote-sha256", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--expected-remote-row-count", type=int, required=True)
    parser.add_argument("--expected-candidate-row-count", type=int, required=True)
    args = parser.parse_args(argv)
    result = reconcile_files(
        args.remote_export,
        args.candidate,
        args.delta,
        expected_remote_sha256=args.expected_remote_sha256,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_remote_row_count=args.expected_remote_row_count,
        expected_candidate_row_count=args.expected_candidate_row_count,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if (result.status == READY and result.delta_written) or result.status == SYNCHRONIZED else 2


if __name__ == "__main__":
    raise SystemExit(main())
