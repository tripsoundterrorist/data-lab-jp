"""Read-only aggregate structure audit for collected FANZA ebook comics."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlsplit

import category_collection_health as health


VERSION = "0.1"
READY = "READY_FOR_EBOOK_COMIC_STRUCTURE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
CONTENT_TYPE = "ebook_comic"


@dataclass(frozen=True)
class ContributorRoleAggregate:
    role: str
    items_with_role: int
    entry_count: int
    complete_entry_count: int
    malformed_entry_count: int


@dataclass(frozen=True)
class EbookComicStructureAudit:
    version: str
    status: str
    item_count: int
    latest_snapshot_count: int
    items_with_title: int
    items_with_release_date: int
    items_with_product_url: int
    items_with_https_image: int
    items_with_series: int
    items_with_genre: int
    items_with_current_price: int
    items_with_list_price: int
    items_with_discount: int
    items_with_review: int
    contributor_roles: tuple[ContributorRoleAggregate, ...]
    malformed_json_item_count: int
    entity_semantics_confirmed: bool
    field_rights_confirmed: bool
    database_write_performed: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["contributor_roles"] = [
            asdict(role) for role in self.contributor_roles
        ]
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> EbookComicStructureAudit:
    return EbookComicStructureAudit(
        VERSION,
        FAIL_CLOSED,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        (),
        0,
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def _https_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _complete_entity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("id"), (str, int))
        and not isinstance(value.get("id"), bool)
        and bool(str(value["id"]).strip())
        and isinstance(value.get("name"), str)
        and bool(value["name"].strip())
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> EbookComicStructureAudit:
    baseline = health.assess(database, config)
    if baseline.status != health.HEALTHY:
        return _failed("CATEGORY_COLLECTION_HEALTH_NOT_READY")
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "WITH latest AS ("
            "SELECT item_id,max(snapshot_id) AS snapshot_id "
            "FROM category_item_snapshots GROUP BY item_id) "
            "SELECT i.title,i.release_date_raw,i.item_url,i.image_json,"
            "i.contributors_json,i.series_json,i.genre_json,"
            "x.current_price_min,x.list_price_min,x.discount_amount,x.review_count "
            "FROM category_items i JOIN category_sources s ON s.source_id=i.source_id "
            "JOIN latest l ON l.item_id=i.item_id "
            "JOIN category_item_snapshots x ON x.snapshot_id=l.snapshot_id "
            "WHERE s.content_type=? ORDER BY i.item_id",
            (CONTENT_TYPE,),
        ).fetchall()
        counts = {
            "title": 0,
            "release": 0,
            "url": 0,
            "image": 0,
            "series": 0,
            "genre": 0,
            "price": 0,
            "list_price": 0,
            "discount": 0,
            "review": 0,
        }
        roles: dict[str, dict[str, int]] = {}
        malformed_items = 0
        for row in rows:
            counts["title"] += isinstance(row["title"], str) and bool(row["title"].strip())
            counts["release"] += isinstance(row["release_date_raw"], str) and bool(row["release_date_raw"].strip())
            counts["url"] += _https_url(row["item_url"])
            item_malformed = False
            try:
                image = json.loads(row["image_json"])
                contributors = json.loads(row["contributors_json"])
                series = json.loads(row["series_json"])
                genre = json.loads(row["genre_json"])
            except (TypeError, json.JSONDecodeError):
                image = contributors = series = genre = None
                item_malformed = True
            if isinstance(image, dict):
                counts["image"] += any(_https_url(value) for value in image.values())
            else:
                item_malformed = True
            if isinstance(series, list):
                counts["series"] += bool(series)
                item_malformed |= any(not _complete_entity(entry) for entry in series)
            else:
                item_malformed = True
            if isinstance(genre, list):
                counts["genre"] += bool(genre)
                item_malformed |= any(not _complete_entity(entry) for entry in genre)
            else:
                item_malformed = True
            if isinstance(contributors, dict):
                for role, entries in contributors.items():
                    if not isinstance(role, str) or not role or not isinstance(entries, list):
                        item_malformed = True
                        continue
                    aggregate = roles.setdefault(
                        role,
                        {"items": 0, "entries": 0, "complete": 0, "malformed": 0},
                    )
                    aggregate["items"] += bool(entries)
                    aggregate["entries"] += len(entries)
                    complete = sum(_complete_entity(entry) for entry in entries)
                    aggregate["complete"] += complete
                    aggregate["malformed"] += len(entries) - complete
                    item_malformed |= complete != len(entries)
            else:
                item_malformed = True
            malformed_items += item_malformed
            counts["price"] += row["current_price_min"] is not None
            counts["list_price"] += row["list_price_min"] is not None
            counts["discount"] += row["discount_amount"] is not None and row["discount_amount"] > 0
            counts["review"] += row["review_count"] is not None
        role_rows = tuple(
            ContributorRoleAggregate(
                role,
                values["items"],
                values["entries"],
                values["complete"],
                values["malformed"],
            )
            for role, values in sorted(roles.items())
        )
        reasons = [
            "EBOOK_COMIC_AGGREGATE_STRUCTURE_AUDITED",
            "CONTRIBUTOR_ROLE_LABELS_NOT_ENTITY_SEMANTICS",
            "FIELD_RIGHTS_REVIEW_REQUIRED",
            "PUBLICATION_REMAINS_CLOSED",
        ]
        if malformed_items:
            reasons.insert(1, "STRUCTURE_GAPS_PRESENT")
        return EbookComicStructureAudit(
            VERSION,
            READY,
            len(rows),
            len(rows),
            counts["title"],
            counts["release"],
            counts["url"],
            counts["image"],
            counts["series"],
            counts["genre"],
            counts["price"],
            counts["list_price"],
            counts["discount"],
            counts["review"],
            role_rows,
            malformed_items,
            False,
            False,
            False,
            False,
            False,
            tuple(reasons),
        )
    except Exception:
        return _failed("EBOOK_COMIC_STRUCTURE_AUDIT_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit aggregate ebook comic structure without publishing."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
