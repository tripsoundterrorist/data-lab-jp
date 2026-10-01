"""Build and verify one product refresh candidate before user approval.

The gate is offline and read-only apart from one review artifact outside the
repository. It never calls an API, writes D1, changes publication, or deploys.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import revenue_mvp_product_card_reconciliation as cards
import revenue_mvp_product_refresh_candidate as candidate_builder
import revenue_mvp_product_refresh_rehearsal as rehearsal
from revenue_mvp_unordered_review_packet import parse_timestamp


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql"
VERSION = "0.1"
READY = "PRODUCT_REFRESH_READY_FOR_EXPLICIT_APPROVAL"
BLOCKED = "BLOCKED"
MAX_NEW_ROUTE_REVALIDATION_AGE = timedelta(hours=48)
ROUTE_PATTERN = re.compile(rb'href="/go/(itm_[0-9a-f]{24})"')


class GateBlocked(ValueError):
    """Fail closed with a fixed, non-sensitive operator reason code."""


@dataclass(frozen=True)
class PreapprovalResult:
    version: str
    status: str
    source_db_sha256: str | None
    source_artifact_sha256: str | None
    candidate_sha256: str | None
    retained_count: int
    added_count: int
    removed_count: int
    candidate_count: int
    d1_lookup_matches: int
    d1_eligible_matches: int
    d1_redirect_matches: int
    d1_runtime_redirect_matches: int
    new_routes_freshly_revalidated: int
    candidate_written: bool
    publication_allowed: bool = False
    production_write_performed: bool = False
    d1_write_performed: bool = False
    explicit_user_approval_required: bool = True
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> PreapprovalResult:
    return PreapprovalResult(
        VERSION, BLOCKED, None, None, None, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        False, reason_codes=(reason,),
    )


def _outside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return False
    except ValueError:
        return True


def _load_private_d1_export(connection: sqlite3.Connection, sql: bytes) -> None:
    allowed_tables = {
        "affiliate_item_lookup",
        "affiliate_redirect_target",
        "affiliate_lifecycle_revalidation_event",
        "sqlite_sequence",
    }

    def authorize(action: int, arg1: str | None, arg2: str | None, *_: Any) -> int:
        if action == sqlite3.SQLITE_INSERT and arg1 in allowed_tables:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and arg1 in allowed_tables:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_UPDATE and arg1 == "sqlite_sequence":
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and arg2 in {"length", "substr", "glob"}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_TRANSACTION:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and arg1 == "defer_foreign_keys":
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    connection.set_authorizer(authorize)
    connection.executescript(sql.decode("utf-8"))
    connection.set_authorizer(lambda *_: sqlite3.SQLITE_OK)


def assess(
    source: Path,
    database: Path,
    d1_export: Path,
    output: Path,
    *,
    expected_db_sha256: str,
    expected_d1_sha256: str,
    evaluated_at: datetime,
    expected_count: int = 100,
) -> PreapprovalResult:
    connection: sqlite3.Connection | None = None
    try:
        if (
            evaluated_at.tzinfo is None or expected_count <= 0
            or any(path.is_symlink() for path in (source, database, d1_export, output))
            or not _outside_repository(d1_export) or not _outside_repository(output)
            or output.exists()
        ):
            return _blocked("INPUT_BOUNDARY_INVALID")
        db_bytes = database.read_bytes()
        d1_bytes = d1_export.read_bytes()
        if hashlib.sha256(db_bytes).hexdigest() != expected_db_sha256:
            return _blocked("DATABASE_IDENTITY_MISMATCH")
        if hashlib.sha256(d1_bytes).hexdigest() != expected_d1_sha256:
            return _blocked("D1_EXPORT_IDENTITY_MISMATCH")

        rotation = rehearsal.assess(
            source, database, evaluated_at=evaluated_at,
            expected_count=expected_count,
        )
        if rotation.status != "READY_FOR_SEPARATE_REFRESH_CANDIDATE":
            return _blocked("REFRESH_REHEARSAL_BLOCKED")
        build = candidate_builder.build_candidate(
            database, expected_db_sha256, evaluated_at, output,
            expected_count=expected_count,
        )
        if build.status != candidate_builder.READY or not output.is_file():
            return _blocked("CANDIDATE_BUILD_BLOCKED")

        candidate_bytes = output.read_bytes()
        candidate_ids = {value.decode("ascii") for value in ROUTE_PATTERN.findall(candidate_bytes)}
        current_ids = {card.public_id for card in cards.reconcile(source.read_bytes(), database)}
        if len(candidate_ids) != expected_count or len(current_ids) != expected_count:
            raise GateBlocked("SURFACE_IDENTITY_INVALID")
        added_ids = candidate_ids - current_ids

        connection = sqlite3.connect(":memory:")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        _load_private_d1_export(connection, d1_bytes)
        placeholders = ",".join("?" for _ in candidate_ids)
        params = tuple(sorted(candidate_ids))
        lookup = connection.execute(
            f"SELECT count(*) FROM affiliate_item_lookup WHERE public_id IN ({placeholders})",
            params,
        ).fetchone()[0]
        eligible = connection.execute(
            f"SELECT count(*) FROM affiliate_runtime_eligible_lookup WHERE public_id IN ({placeholders})",
            params,
        ).fetchone()[0]
        redirect = connection.execute(
            f"SELECT count(*) FROM affiliate_redirect_target WHERE public_id IN ({placeholders})",
            params,
        ).fetchone()[0]
        runtime = connection.execute(
            f"SELECT count(*) FROM affiliate_runtime_redirect_target WHERE public_id IN ({placeholders})",
            params,
        ).fetchone()[0]

        fresh = 0
        now = evaluated_at.astimezone(timezone.utc)
        for public_id in sorted(added_ids):
            event = connection.execute(
                """SELECT checked_at,outcome,affiliate_enabled_after
                   FROM affiliate_lifecycle_revalidation_event
                   WHERE public_id=? ORDER BY checked_at DESC,id DESC LIMIT 1""",
                (public_id,),
            ).fetchone()
            if event is None or event[1:] != ("VALID", 1):
                raise GateBlocked("NEW_ROUTE_REVALIDATION_MISSING")
            checked = rehearsal._timestamp(event[0])
            age = now - checked
            if age < timedelta(0) or age > MAX_NEW_ROUTE_REVALIDATION_AGE:
                raise GateBlocked("NEW_ROUTE_REVALIDATION_STALE")
            fresh += 1

        if (lookup, eligible, redirect, runtime) != (expected_count,) * 4:
            raise GateBlocked("D1_RUNTIME_COVERAGE_INCOMPLETE")
        return PreapprovalResult(
            VERSION, READY, expected_db_sha256,
            hashlib.sha256(source.read_bytes()).hexdigest(),
            hashlib.sha256(candidate_bytes).hexdigest(),
            rotation.retained_count or 0, rotation.added_count or 0,
            rotation.removed_count or 0, expected_count,
            lookup, eligible, redirect, runtime, fresh, True,
            reason_codes=(
                "OFFICIAL_COLLECTION_INPUT_VERIFIED",
                "CANDIDATE_D1_RUNTIME_COVERAGE_VERIFIED",
                "NEW_ROUTES_FRESHLY_REVALIDATED",
                "EXPLICIT_PRODUCTION_APPROVAL_REQUIRED",
            ),
        )
    except GateBlocked as error:
        try:
            if output.exists():
                output.unlink()
        except OSError:
            pass
        return _blocked(str(error))
    except (OSError, UnicodeError, sqlite3.Error, ValueError, TypeError):
        try:
            if output.exists():
                output.unlink()
        except OSError:
            pass
        return _blocked("PREAPPROVAL_GATE_FAILED")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--d1-export", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-db-sha256", required=True)
    parser.add_argument("--expected-d1-sha256", required=True)
    parser.add_argument("--evaluated-at", required=True, type=parse_timestamp)
    parser.add_argument("--expected-count", type=int, default=100)
    args = parser.parse_args(argv)
    result = assess(
        args.source, args.db, args.d1_export, args.output,
        expected_db_sha256=args.expected_db_sha256,
        expected_d1_sha256=args.expected_d1_sha256,
        evaluated_at=args.evaluated_at,
        expected_count=args.expected_count,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
