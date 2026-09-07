"""Create a private, disabled-only D1 lookup import candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from affiliate_runtime_dmm_connector import CONTENT_ID, _public_item_id


EXPORT_VERSION = "0.1"
EXPORTED = "EXPORTED"
FAIL_CLOSED = "FAIL_CLOSED"
EXPECTED_SCOPE = ("FANZA", "digital", "videoa")


@dataclass(frozen=True)
class ExportResult:
    export_version: str
    status: str
    row_count: int
    all_rows_disabled: bool
    source_query_only: bool
    output_sha256: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    reasons: tuple[str, ...],
    *,
    rows: int = 0,
    digest: str | None = None,
) -> ExportResult:
    return ExportResult(
        EXPORT_VERSION, status, rows, status == EXPORTED, True, digest, reasons
    )


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def export_candidate(
    database_path: Path,
    output_path: Path,
    *,
    allowed_output_root: Path,
) -> ExportResult:
    """Read one SQLite source query-only and atomically write a private SQL file."""

    connection: sqlite3.Connection | None = None
    temporary_path: Path | None = None
    try:
        source = database_path.resolve()
        root = allowed_output_root.resolve()
        target = output_path.resolve()
        if not source.is_file():
            return _result(FAIL_CLOSED, ("SOURCE_DATABASE_UNAVAILABLE",))
        if target.parent != root or target.suffix.lower() != ".sql":
            return _result(FAIL_CLOSED, ("OUTPUT_TARGET_FORBIDDEN",))
        root.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            return _result(FAIL_CLOSED, ("OUTPUT_TARGET_ALREADY_EXISTS",))

        connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        records = connection.execute(
            "SELECT site, service, floor, content_id FROM items ORDER BY site, service, floor, content_id"
        ).fetchall()
        if not records:
            return _result(FAIL_CLOSED, ("SOURCE_ITEMS_EMPTY",))

        rows: list[tuple[str, str]] = []
        seen_public: set[str] = set()
        seen_content: set[str] = set()
        for record in records:
            if len(record) != 4 or not all(isinstance(value, str) for value in record):
                return _result(FAIL_CLOSED, ("SOURCE_ROW_INVALID",))
            site, service, floor, content_id = record
            if (site, service, floor) != EXPECTED_SCOPE:
                return _result(FAIL_CLOSED, ("SOURCE_SCOPE_UNSUPPORTED",))
            if CONTENT_ID.fullmatch(content_id) is None:
                return _result(FAIL_CLOSED, ("SOURCE_CONTENT_ID_INVALID",))
            public_id = _public_item_id(site, service, floor, content_id)
            if public_id in seen_public or content_id in seen_content:
                return _result(FAIL_CLOSED, ("SOURCE_IDENTIFIER_NOT_UNIQUE",))
            seen_public.add(public_id)
            seen_content.add(content_id)
            rows.append((public_id, content_id))

        statements = ["BEGIN TRANSACTION;"]
        for public_id, content_id in rows:
            statements.append(
                "INSERT INTO affiliate_item_lookup "
                "(public_id, content_id, updated_at) VALUES "
                f"({_quote(public_id)}, {_quote(content_id)}, '1970-01-01T00:00:00Z');"
            )
        statements.append("COMMIT;")
        payload = ("\n".join(statements) + "\n").encode("utf-8")

        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix=".affiliate-lookup-", suffix=".tmp", delete=False
        )
        temporary_path = Path(handle.name)
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, target)
        temporary_path = None
        return _result(
            EXPORTED,
            ("PRIVATE_DISABLED_LOOKUP_EXPORTED",),
            rows=len(rows),
            digest=hashlib.sha256(payload).hexdigest(),
        )
    except (OSError, sqlite3.Error):
        return _result(FAIL_CLOSED, ("EXPORT_OPERATION_FAILED",))
    except Exception:
        return _result(FAIL_CLOSED, ("EXPORT_INTERNAL_ERROR",))
    finally:
        if connection is not None:
            connection.close()
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


__all__ = ["EXPORTED", "EXPORT_VERSION", "ExportResult", "FAIL_CLOSED", "export_candidate"]
