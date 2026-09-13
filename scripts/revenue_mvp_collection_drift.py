"""Classify post-collection Revenue MVP evidence drift without mutation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import affiliate_d1_production_state as d1_state
import revenue_mvp_publication_artifact_evidence as artifact_evidence


VERSION = "0.1"
IN_SYNC = "IN_SYNC"
SYNC_REQUIRED = "SYNC_REQUIRED_FAIL_CLOSED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class CollectionDrift:
    version: str
    status: str
    database_item_count: int | None
    receipt_item_count: int | None
    d1_evidence_row_count: int | None
    database_identity_matches_receipt: bool
    artifact_refresh_required: bool
    d1_lookup_refresh_required: bool
    publication_allowed: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(reason: str) -> CollectionDrift:
    return CollectionDrift(
        VERSION, FAIL_CLOSED, None, None, None, False, False, False,
        False, False, (reason,),
    )


def assess(
    database: Path = artifact_evidence.DB,
    receipt_path: Path = artifact_evidence.RECEIPT,
    d1_row_count: int = d1_state.EXPECTED_ROW_COUNT,
) -> CollectionDrift:
    connection: sqlite3.Connection | None = None
    try:
        if database.is_symlink() or receipt_path.is_symlink():
            return _failed("UNSAFE_INPUT_PATH")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_count = receipt.get("item_count")
        receipt_digest = receipt.get("source_db_sha256")
        if (
            type(receipt_count) is not int or receipt_count <= 0
            or not isinstance(receipt_digest, str) or len(receipt_digest) != 64
            or type(d1_row_count) is not int or d1_row_count < 0
            or receipt.get("publication_allowed") is not False
            or receipt.get("production_write_performed") is not False
            or receipt.get("gate_unlock_allowed") is not False
        ):
            return _failed("EVIDENCE_INPUT_INVALID")
        database_bytes = database.read_bytes()
        digest_matches = hashlib.sha256(database_bytes).hexdigest() == receipt_digest
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            return _failed("DATABASE_INTEGRITY_FAILED")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            return _failed("DATABASE_FOREIGN_KEY_FAILED")
        database_count = connection.execute("SELECT count(*) FROM items").fetchone()[0]
        if database_count < receipt_count or d1_row_count > database_count:
            return _failed("NON_MONOTONIC_EVIDENCE")
        artifact_refresh = not digest_matches or database_count != receipt_count
        d1_refresh = database_count != d1_row_count
        if not artifact_refresh and not d1_refresh:
            return CollectionDrift(
                VERSION, IN_SYNC, database_count, receipt_count, d1_row_count,
                True, False, False, False, False,
                ("CURRENT_EVIDENCE_SYNCHRONIZED",),
            )
        reasons = ["PUBLICATION_REMAINS_CLOSED"]
        if artifact_refresh:
            reasons.append("ARTIFACT_REFRESH_REQUIRED")
        if d1_refresh:
            reasons.append("D1_LOOKUP_REFRESH_REQUIRES_SEPARATE_APPROVAL")
        return CollectionDrift(
            VERSION, SYNC_REQUIRED, database_count, receipt_count, d1_row_count,
            digest_matches, artifact_refresh, d1_refresh, False, False,
            tuple(reasons),
        )
    except Exception:
        return _failed("COLLECTION_DRIFT_CHECK_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main() -> int:
    result = assess()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {IN_SYNC, SYNC_REQUIRED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
