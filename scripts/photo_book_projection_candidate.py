"""Pure fail-closed validator for a non-public photo-book projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
import re
from typing import Any
from urllib.parse import urlsplit


VERSION = "0.1"
READY = "READY_FOR_FIELD_AND_SEMANTICS_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
PRODUCT_HOST = "book.dmm.com"
TOP_LEVEL_FIELDS = frozenset(
    {
        "projection_version",
        "public_id",
        "source",
        "title",
        "release_date_raw",
        "current_price",
        "list_price",
        "actors",
        "authors",
        "manufactures",
        "series",
        "genres",
        "source_product_url",
        "review",
        "observed_at",
        "data_freshness",
    }
)
SOURCE_FIELDS = frozenset({"site", "service", "floor", "content_type", "content_id"})
ENTITY_FIELDS = frozenset({"id", "name"})
REVIEW_FIELDS = frozenset({"average", "count"})


@dataclass(frozen=True)
class PhotoBookProjectionCandidateResult:
    version: str
    status: str
    structure_valid: bool
    exact_field_allowlist: bool
    image_field_absent: bool
    contributor_semantics_confirmed: bool
    field_rights_confirmed: bool
    compliance_approved: bool
    publication_allowed: bool
    affiliate_activation_allowed: bool
    sitemap_change_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(valid: bool, reasons: tuple[str, ...]) -> PhotoBookProjectionCandidateResult:
    return PhotoBookProjectionCandidateResult(
        VERSION,
        READY if valid else FAIL_CLOSED,
        valid,
        valid,
        valid,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        reasons,
    )


def _exact_mapping(value: Any, fields: frozenset[str]) -> bool:
    return isinstance(value, dict) and frozenset(value) == fields


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _entity_list(value: Any, *, required: bool) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not required)
        and all(
            _exact_mapping(entry, ENTITY_FIELDS)
            and isinstance(entry["id"], (str, int))
            and not isinstance(entry["id"], bool)
            and bool(str(entry["id"]).strip())
            and _text(entry["name"])
            for entry in value
        )
    )


def _product_url(value: Any) -> bool:
    if not _text(value):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == PRODUCT_HOST
        and parsed.username is None
        and parsed.password is None
    )


def _money(value: Any, *, optional: bool = False) -> bool:
    return (optional and value is None) or (type(value) is int and value >= 0)


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


def _review(value: Any) -> bool:
    if not _exact_mapping(value, REVIEW_FIELDS):
        return False
    average = value["average"]
    count = value["count"]
    if average is None and count is None:
        return True
    return (
        isinstance(average, (int, float))
        and not isinstance(average, bool)
        and math.isfinite(float(average))
        and average >= 0
        and type(count) is int
        and count >= 0
    )


def assess(value: Any) -> PhotoBookProjectionCandidateResult:
    if not _exact_mapping(value, TOP_LEVEL_FIELDS):
        return _result(False, ("PROJECTION_FIELD_ALLOWLIST_MISMATCH",))
    source = value["source"]
    if not _exact_mapping(source, SOURCE_FIELDS):
        return _result(False, ("SOURCE_NAMESPACE_INVALID",))
    if (
        value["projection_version"] != VERSION
        or source["site"] != "DMM.com"
        or source["service"] != "ebook"
        or source["floor"] != "photo"
        or source["content_type"] != "photo_book"
        or not _text(source["content_id"])
        or not isinstance(value["public_id"], str)
        or re.fullmatch(r"pbk_[0-9a-f]{24}", value["public_id"]) is None
    ):
        return _result(False, ("PROJECTION_IDENTITY_INVALID",))
    if not (
        _text(value["title"])
        and _text(value["release_date_raw"])
        and _money(value["current_price"])
        and _money(value["list_price"], optional=True)
        and _review(value["review"])
    ):
        return _result(False, ("PROJECTION_CORE_FIELD_INVALID",))
    if not (
        _entity_list(value["actors"], required=True)
        and _entity_list(value["authors"], required=True)
        and _entity_list(value["manufactures"], required=True)
        and _entity_list(value["series"], required=True)
        and _entity_list(value["genres"], required=False)
    ):
        return _result(False, ("PROJECTION_ENTITY_REFERENCE_INVALID",))
    if not (
        _product_url(value["source_product_url"])
        and _timestamp(value["observed_at"])
        and value["data_freshness"] in {"CURRENT", "STALE"}
    ):
        return _result(False, ("PROJECTION_SOURCE_FACT_INVALID",))
    return _result(
        True,
        (
            "STRUCTURE_ONLY_CANDIDATE_VALIDATED",
            "DMM_BOOKS_PRODUCT_IMAGE_EXCLUDED",
            "ACTOR_AUTHOR_AND_MANUFACTURE_SEMANTICS_REVIEW_REQUIRED",
            "FIELD_RIGHTS_AND_COMPLIANCE_REVIEW_REQUIRED",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )
