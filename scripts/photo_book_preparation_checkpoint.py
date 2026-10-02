"""Read-only boundary audit and synthetic rehearsal for DMM photo books."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

import category_collection_health as health
import photo_book_projection_candidate as projection


VERSION = "0.1"
READY = "READY_FOR_OFFICIAL_RESPONSE"
FAIL_CLOSED = "FAIL_CLOSED"
PRODUCT_HOST = "book.dmm.com"
RELEASE_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?"
)


@dataclass(frozen=True)
class PhotoBookPreparationCheckpoint:
    version: str
    status: str
    item_count: int
    source_namespace_valid_count: int
    product_url_boundary_valid_count: int
    release_datetime_valid_count: int
    unique_public_id_count: int
    public_id_collision_count: int
    synthetic_scenario_count: int
    synthetic_scenario_pass_count: int
    synthetic_forbidden_host_blocked: bool
    synthetic_forbidden_image_blocked: bool
    image_data_read: bool
    artifact_created: bool
    database_write_performed: bool
    external_io_performed: bool
    compliance_approved: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(
    *,
    status: str,
    reasons: tuple[str, ...],
    item_count: int = 0,
    namespace_count: int = 0,
    product_count: int = 0,
    release_count: int = 0,
    unique_id_count: int = 0,
    collision_count: int = 0,
    scenario_count: int = 0,
    scenario_pass_count: int = 0,
    forbidden_host_blocked: bool = False,
    forbidden_image_blocked: bool = False,
) -> PhotoBookPreparationCheckpoint:
    return PhotoBookPreparationCheckpoint(
        VERSION, status, item_count, namespace_count, product_count,
        release_count, unique_id_count, collision_count, scenario_count,
        scenario_pass_count, forbidden_host_blocked, forbidden_image_blocked,
        False, False, False, False, False, False, False, reasons,
    )


def _https_product_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == PRODUCT_HOST
        and parsed.username is None
        and parsed.password is None
    )


def _release_datetime(value: Any) -> bool:
    if not isinstance(value, str) or RELEASE_PATTERN.fullmatch(value) is None:
        return False
    normalized = value.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        datetime.fromisoformat(normalized)
        return True
    except ValueError:
        return False


def _public_id(source: dict[str, str]) -> str:
    canonical = "\x1f".join(
        source[key]
        for key in ("site", "service", "floor", "content_type", "content_id")
    )
    return "pbk_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _synthetic_candidate(content_id: str, *, review: dict[str, Any], genres: list) -> dict:
    source = {
        "site": "DMM.com",
        "service": "ebook",
        "floor": "photo",
        "content_type": "photo_book",
        "content_id": content_id,
    }
    return {
        "projection_version": projection.VERSION,
        "public_id": _public_id(source),
        "source": source,
        "title": "Synthetic title",
        "release_date_raw": "2026-01-01 00:00:00",
        "current_price": 100,
        "list_price": None,
        "actors": [{"id": "actor-1", "name": "Synthetic actor"}],
        "authors": [{"id": "author-1", "name": "Synthetic author"}],
        "manufactures": [{"id": "maker-1", "name": "Synthetic maker"}],
        "series": [{"id": "series-1", "name": "Synthetic series"}],
        "genres": genres,
        "source_product_url": f"https://{PRODUCT_HOST}/synthetic",
        "review": review,
        "observed_at": "2026-10-02T00:00:00+09:00",
        "data_freshness": "CURRENT",
    }


def _run_synthetic_rehearsal() -> tuple[int, int, bool, bool]:
    scenarios = (
        ({"average": 4.0, "count": 3}, [{"id": "genre-1", "name": "Genre"}]),
        ({"average": None, "count": None}, []),
    )
    passed = 0
    for index, (review, genres) in enumerate(scenarios, start=1):
        candidate = _synthetic_candidate(
            f"synthetic-{index}", review=review, genres=genres
        )
        passed += (
            _https_product_url(candidate["source_product_url"])
            and _release_datetime(candidate["release_date_raw"])
            and projection.assess(candidate).status == projection.READY
        )
    forbidden_host = _synthetic_candidate(
        "forbidden-host", review={"average": None, "count": None}, genres=[]
    )
    forbidden_host["source_product_url"] = "https://example.invalid/item"
    forbidden_host_blocked = projection.assess(forbidden_host).status == projection.FAIL_CLOSED
    forbidden_image = _synthetic_candidate(
        "forbidden-image", review={"average": None, "count": None}, genres=[]
    )
    forbidden_image["image"] = "https://example.invalid/image.jpg"
    forbidden_image_blocked = projection.assess(forbidden_image).status == projection.FAIL_CLOSED
    return len(scenarios), passed, forbidden_host_blocked, forbidden_image_blocked


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> PhotoBookPreparationCheckpoint:
    baseline = health.assess(database, config)
    if baseline.status != health.HEALTHY:
        return _result(
            status=FAIL_CLOSED,
            reasons=("CATEGORY_COLLECTION_HEALTH_NOT_READY",),
        )
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT s.site,s.service,s.floor,s.content_type,i.content_id,"
            "i.item_url,i.release_date_raw "
            "FROM category_items i JOIN category_sources s ON s.source_id=i.source_id "
            "WHERE s.content_type='photo_book' ORDER BY i.item_id"
        ).fetchall()
        namespace_count = 0
        product_count = 0
        release_count = 0
        public_ids: list[str] = []
        for row in rows:
            source = {
                key: row[key]
                for key in ("site", "service", "floor", "content_type", "content_id")
            }
            namespace_count += (
                source["site"] == "DMM.com"
                and source["service"] == "ebook"
                and source["floor"] == "photo"
                and source["content_type"] == "photo_book"
                and isinstance(source["content_id"], str)
                and bool(source["content_id"].strip())
            )
            product_count += _https_product_url(row["item_url"])
            release_count += _release_datetime(row["release_date_raw"])
            public_ids.append(_public_id(source))
        unique_count = len(set(public_ids))
        collision_count = len(public_ids) - unique_count
        scenario_count, scenario_pass_count, host_blocked, image_blocked = (
            _run_synthetic_rehearsal()
        )
        total = len(rows)
        complete = (
            total > 0
            and namespace_count == total
            and product_count == total
            and release_count == total
            and unique_count == total
            and collision_count == 0
            and scenario_pass_count == scenario_count
            and host_blocked
            and image_blocked
        )
        return _result(
            status=READY if complete else FAIL_CLOSED,
            reasons=(
                (
                    "PHOTO_BOOK_PREPARATION_CHECKPOINT_COMPLETE"
                    if complete
                    else "PHOTO_BOOK_PREPARATION_BOUNDARY_OR_REHEARSAL_BLOCKED"
                ),
                "DMM_BOOKS_PRODUCT_IMAGE_NOT_READ_OR_PROJECTED",
                "OFFICIAL_RESPONSE_AND_COMPLIANCE_REVIEW_REQUIRED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
            item_count=total,
            namespace_count=namespace_count,
            product_count=product_count,
            release_count=release_count,
            unique_id_count=unique_count,
            collision_count=collision_count,
            scenario_count=scenario_count,
            scenario_pass_count=scenario_pass_count,
            forbidden_host_blocked=host_blocked,
            forbidden_image_blocked=image_blocked,
        )
    except Exception:
        return _result(
            status=FAIL_CLOSED,
            reasons=("PHOTO_BOOK_PREPARATION_CHECKPOINT_ERROR",),
        )
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit photo-book boundaries and run a synthetic rehearsal."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
