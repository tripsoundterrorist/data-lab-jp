"""Read-only identity and integrity preflight for a handed-off Revenue MVP DB."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from revenue_mvp_db_audit import READY as DB_READY, audit_database


VERSION = "0.1"
READY = "HANDOFF_READY"
BLOCKED = "BLOCKED"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class HandoffResult:
    version: str
    status: str
    read_only: bool
    database_present: bool
    identity_verified: bool
    database_status: str
    items_count: int | None
    item_snapshots_count: int | None
    collection_runs_count: int | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def preflight(path: Path, expected_sha256: Any) -> HandoffResult:
    reasons: set[str] = set()
    identity = False
    if path.is_symlink():
        return HandoffResult(
            VERSION, BLOCKED, True, False, False, "NOT_RUN",
            None, None, None, ("UNSAFE_DATABASE_ENTRY",),
        )
    audit = audit_database(path)
    try:
        resolved = path.resolve(strict=True)
        if not path.is_file():
            reasons.add("UNSAFE_DATABASE_ENTRY")
        if not isinstance(expected_sha256, str) or not SHA256_PATTERN.fullmatch(expected_sha256):
            reasons.add("EXPECTED_SHA256_REQUIRED")
        elif resolved.is_file():
            def digest() -> str:
                value = sha256()
                with resolved.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        value.update(block)
                return value.hexdigest()

            before = digest()
            audit = audit_database(path)
            after = digest()
            if before != after:
                reasons.add("DATABASE_CHANGED_DURING_PREFLIGHT")
            identity = before == after == expected_sha256
            if not identity:
                reasons.add("DATABASE_IDENTITY_MISMATCH")
    except (OSError, RuntimeError):
        reasons.add("DATABASE_UNAVAILABLE")
    if audit.status != DB_READY:
        reasons.update(audit.reason_codes)
    ready = not reasons and identity and audit.status == DB_READY
    return HandoffResult(
        VERSION, READY if ready else BLOCKED, True, audit.database_present,
        identity, audit.status, audit.items_count, audit.item_snapshots_count,
        audit.collection_runs_count, tuple(sorted(reasons)) or ("DB_HANDOFF_VERIFIED",),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a DATA LAB DB handoff without writes.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    result = preflight(args.db, args.expected_sha256)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
