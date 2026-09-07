"""Read-only preflight for a private affiliate lookup export candidate."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from affiliate_runtime_dmm_connector import CONTENT_ID, _public_item_id
from revenue_mvp_db_handoff_preflight import READY as HANDOFF_READY, preflight as handoff_preflight


VERSION = "0.1"
READY = "PREFLIGHT_READY"
BLOCKED = "BLOCKED"
EXPECTED_SCOPE = ("FANZA", "digital", "videoa")


@dataclass(frozen=True)
class ExportPreflightResult:
    version: str
    status: str
    database_identity_verified: bool
    source_query_only: bool
    item_count: int | None
    supported_item_count: int | None
    scope_exact: bool
    identifiers_valid: bool
    identifiers_unique: bool
    export_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(reasons: tuple[str, ...], **changes: Any) -> ExportPreflightResult:
    values = {
        "version": VERSION,
        "status": BLOCKED,
        "database_identity_verified": False,
        "source_query_only": False,
        "item_count": None,
        "supported_item_count": None,
        "scope_exact": False,
        "identifiers_valid": False,
        "identifiers_unique": False,
        "export_performed": False,
        "publication_allowed": False,
        "reason_codes": reasons,
    }
    values.update(changes)
    return ExportPreflightResult(**values)


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate(database_path: Path, expected_sha256: Any) -> ExportPreflightResult:
    """Validate export eligibility without writing SQL or exposing identifiers."""

    handoff = handoff_preflight(database_path, expected_sha256)
    if handoff.status != HANDOFF_READY or not handoff.identity_verified:
        return _result(
            tuple(handoff.reason_codes),
            database_identity_verified=handoff.identity_verified,
        )

    connection: sqlite3.Connection | None = None
    try:
        path = database_path.resolve(strict=True)
        before = _digest(path)
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        query_only = connection.execute("PRAGMA query_only").fetchone() == (1,)
        if not query_only:
            return _result(
                ("READ_ONLY_ENFORCEMENT_FAILED",),
                database_identity_verified=True,
            )

        records = connection.execute(
            "SELECT site, service, floor, content_id "
            "FROM items ORDER BY site, service, floor, content_id"
        ).fetchall()
        total = len(records)
        supported = 0
        identifiers_valid = True
        seen_public: set[str] = set()
        seen_content: set[str] = set()
        identifiers_unique = True
        for record in records:
            if len(record) != 4 or not all(isinstance(value, str) for value in record):
                identifiers_valid = False
                continue
            site, service, floor, content_id = record
            if (site, service, floor) != EXPECTED_SCOPE:
                continue
            supported += 1
            if CONTENT_ID.fullmatch(content_id) is None:
                identifiers_valid = False
                continue
            public_id = _public_item_id(site, service, floor, content_id)
            if content_id in seen_content or public_id in seen_public:
                identifiers_unique = False
            seen_content.add(content_id)
            seen_public.add(public_id)

        after = _digest(path)
        identity_stable = before == after == expected_sha256
        reasons: list[str] = []
        if not identity_stable:
            reasons.append("DATABASE_CHANGED_DURING_EXPORT_PREFLIGHT")
        if total <= 0:
            reasons.append("SOURCE_ITEMS_EMPTY")
        if supported != total:
            reasons.append("SOURCE_SCOPE_UNSUPPORTED")
        if not identifiers_valid:
            reasons.append("SOURCE_CONTENT_ID_INVALID")
        if not identifiers_unique:
            reasons.append("SOURCE_IDENTIFIER_NOT_UNIQUE")
        ready = not reasons
        return _result(
            tuple(sorted(reasons)) if reasons else ("PRIVATE_EXPORT_REVIEW_READY",),
            status=READY if ready else BLOCKED,
            database_identity_verified=identity_stable,
            source_query_only=True,
            item_count=total,
            supported_item_count=supported,
            scope_exact=total > 0 and supported == total,
            identifiers_valid=identifiers_valid,
            identifiers_unique=identifiers_unique,
        )
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return _result(
            ("EXPORT_PREFLIGHT_OPERATION_FAILED",),
            database_identity_verified=True,
        )
    except Exception:
        return _result(
            ("EXPORT_PREFLIGHT_INTERNAL_ERROR",),
            database_identity_verified=True,
        )
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a private affiliate lookup export candidate without writes."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    result = evaluate(args.db, args.expected_sha256)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
