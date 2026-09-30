"""Export the exact newest 300-item run as a private disabled D1 candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from affiliate_runtime_dmm_connector import CONTENT_ID, _public_item_id
import revenue_mvp_expansion_page_validator as page_validator


VERSION = "0.1"
EXPORTED = "EXPANSION_LOOKUP_EXPORTED"
BLOCKED = "BLOCKED"
EXPECTED_SCOPE = ("FANZA", "digital", "videoa")


@dataclass(frozen=True)
class ExportReceipt:
    version: str
    status: str
    row_count: int
    all_rows_disabled: bool
    source_identity_verified: bool
    output_sha256: str | None
    d1_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> ExportReceipt:
    return ExportReceipt(VERSION, BLOCKED, 0, True, False, None, False, False, (reason,))


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def export(
    database: Path,
    output: Path,
    *,
    private_root: Path,
    expected_database_sha256: str,
) -> ExportReceipt:
    connection: sqlite3.Connection | None = None
    temporary: Path | None = None
    try:
        if (
            database.is_symlink() or output.is_symlink() or private_root.is_symlink()
            or not database.is_file() or not private_root.is_dir()
            or output.parent.resolve() != private_root.resolve()
            or output.suffix.lower() != ".sql" or output.exists()
            or len(expected_database_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_database_sha256)
        ):
            return _blocked("INPUT_BOUNDARY_INVALID")
        before = _digest(database)
        if before != expected_database_sha256:
            return _blocked("DATABASE_IDENTITY_MISMATCH")
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        run = connection.execute(
            "SELECT * FROM collection_runs WHERE run_type='native' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None or (
            run["status"] != "success" or run["max_items"] != 300
            or run["max_pages"] != 6 or run["api_calls"] != 6
            or run["pages_fetched"] != 6 or run["processed_items"] != 300
            or run["snapshots_inserted"] != 300
            or run["duplicate_content_ids_across_pages"] != 0
        ):
            return _blocked("LATEST_RUN_CONTRACT_INVALID")
        records = connection.execute(
            """SELECT s.source_offset,s.source_position,
                      i.site,i.service,i.floor,i.content_id
               FROM item_snapshots s JOIN items i ON i.id=s.item_id
               WHERE s.collection_run_id=?
               ORDER BY s.source_offset,s.source_position,s.id""",
            (run["collection_run_id"],),
        ).fetchall()
        grouped: dict[int, list[str]] = {}
        rows: list[tuple[str, str]] = []
        public_ids: set[str] = set()
        content_ids: set[str] = set()
        for record in records:
            identity = (record["site"], record["service"], record["floor"])
            content_id = record["content_id"]
            if identity != EXPECTED_SCOPE or type(content_id) is not str or CONTENT_ID.fullmatch(content_id) is None:
                return _blocked("SOURCE_ROW_INVALID")
            public_id = _public_item_id(*identity, content_id)
            if public_id in public_ids or content_id in content_ids:
                return _blocked("SOURCE_IDENTIFIER_NOT_UNIQUE")
            public_ids.add(public_id)
            content_ids.add(content_id)
            grouped.setdefault(record["source_offset"], []).append(content_id)
            rows.append((public_id, content_id))
        pages = tuple(
            page_validator.PageObservation(offset, 50, len(values), tuple(values))
            for offset, values in sorted(grouped.items())
        )
        if len(rows) != 300 or page_validator.validate(pages).status != page_validator.PASS:
            return _blocked("EXACT_300_PAGE_VALIDATION_FAILED")
        if _digest(database) != before:
            return _blocked("DATABASE_CHANGED_DURING_EXPORT")

        statements = ["BEGIN TRANSACTION;"]
        statements.extend(
            "INSERT INTO affiliate_item_lookup "
            "(public_id, content_id, updated_at) VALUES "
            f"({_quote(public_id)}, {_quote(content_id)}, '1970-01-01T00:00:00Z');"
            for public_id, content_id in rows
        )
        statements.append("COMMIT;")
        payload = ("\n".join(statements) + "\n").encode("utf-8")
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=private_root, prefix=".expansion-lookup-", suffix=".tmp", delete=False
        )
        temporary = Path(handle.name)
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, output)
        temporary = None
        return ExportReceipt(
            VERSION, EXPORTED, 300, True, True,
            hashlib.sha256(payload).hexdigest(), False, False,
            ("PRIVATE_DISABLED_LOOKUP_EXPORTED", "D1_IMPORT_NOT_AUTHORIZED"),
        )
    except (OSError, sqlite3.Error, ValueError):
        return _blocked("EXPORT_FAILED")
    finally:
        if connection is not None:
            connection.close()
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


__all__ = ["ExportReceipt", "export"]
