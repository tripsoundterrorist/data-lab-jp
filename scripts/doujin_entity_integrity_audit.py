"""Aggregate-only integrity audit for doujin entity references."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

import category_collection_health as health


VERSION = "0.1"
READY = "READY_FOR_COLLECTION_ONLY_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
CONTENT_TYPES = ("doujin", "doujin_bl", "doujin_tl")


@dataclass(frozen=True)
class EntityAggregate:
    entity_type: str
    entry_count: int
    entries_with_id_and_name: int
    unique_source_ids: int
    malformed_entry_count: int
    source_ids_with_name_variants: int
    source_ids_in_multiple_content_types: int


@dataclass(frozen=True)
class EntityIntegrityAudit:
    version: str
    status: str
    item_count: int
    entities: tuple[EntityAggregate, ...]
    identity_scope: str
    database_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["entities"] = [asdict(row) for row in self.entities]
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(reason: str) -> EntityIntegrityAudit:
    return EntityIntegrityAudit(
        VERSION, FAIL_CLOSED, 0, (), "SOURCE_SCOPED", False, False, (reason,)
    )


def _entries(entity_type: str, contributors: Any, series: Any, genre: Any) -> Any:
    if entity_type == "maker":
        return contributors.get("maker", []) if isinstance(contributors, dict) else None
    value = series if entity_type == "series" else genre
    return value if isinstance(value, list) else None


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> EntityIntegrityAudit:
    baseline = health.assess(database, config)
    if baseline.status != health.HEALTHY:
        return _failed("CATEGORY_COLLECTION_HEALTH_NOT_READY")
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        placeholders = ",".join("?" for _ in CONTENT_TYPES)
        rows = connection.execute(
            "SELECT s.content_type,i.contributors_json,i.series_json,i.genre_json "
            "FROM category_items i JOIN category_sources s ON s.source_id=i.source_id "
            f"WHERE s.content_type IN ({placeholders})",
            CONTENT_TYPES,
        ).fetchall()
        aggregates: list[EntityAggregate] = []
        for entity_type in ("maker", "series", "genre"):
            entry_count = complete = malformed = 0
            names_by_id: dict[str, set[str]] = {}
            content_types_by_id: dict[str, set[str]] = {}
            for content_type, contributors_raw, series_raw, genre_raw in rows:
                values = _entries(
                    entity_type,
                    json.loads(contributors_raw),
                    json.loads(series_raw),
                    json.loads(genre_raw),
                )
                if values is None:
                    malformed += 1
                    continue
                for value in values:
                    entry_count += 1
                    if not isinstance(value, dict):
                        malformed += 1
                        continue
                    source_id = value.get("id")
                    name = value.get("name")
                    has_id = isinstance(source_id, (str, int)) and bool(str(source_id).strip())
                    has_name = isinstance(name, str) and bool(name.strip())
                    if not (has_id and has_name):
                        malformed += 1
                        continue
                    complete += 1
                    key = str(source_id).strip()
                    names_by_id.setdefault(key, set()).add(name.strip())
                    content_types_by_id.setdefault(key, set()).add(content_type)
            aggregates.append(EntityAggregate(
                entity_type=entity_type,
                entry_count=entry_count,
                entries_with_id_and_name=complete,
                unique_source_ids=len(names_by_id),
                malformed_entry_count=malformed,
                source_ids_with_name_variants=sum(len(v) > 1 for v in names_by_id.values()),
                source_ids_in_multiple_content_types=sum(
                    len(v) > 1 for v in content_types_by_id.values()
                ),
            ))
        reason_codes = ["SOURCE_SCOPED_ENTITY_REFERENCES_AUDITED"]
        if any(row.malformed_entry_count for row in aggregates):
            reason_codes.append("ENTITY_REFERENCE_INTEGRITY_GAPS_PRESENT")
        return EntityIntegrityAudit(
            VERSION, READY, len(rows), tuple(aggregates), "SOURCE_SCOPED", False,
            False, tuple(reason_codes),
        )
    except Exception:
        return _failed("DOUJIN_ENTITY_INTEGRITY_AUDIT_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit doujin entity reference integrity without exposing values."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
