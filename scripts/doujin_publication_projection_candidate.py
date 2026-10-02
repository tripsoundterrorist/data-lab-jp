"""Pure fail-closed validator for a non-public doujin projection candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import urlsplit


VERSION = "0.1"
READY = "READY_FOR_FIELD_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
CONTENT_TYPES = frozenset(("doujin", "doujin_bl", "doujin_tl"))
TOP_LEVEL_FIELDS = frozenset((
    "projection_version", "public_id", "source", "title", "release_date_raw",
    "current_price", "list_price", "discount_amount", "discount_rate",
    "makers", "series", "genres", "image", "source_product_url",
    "observed_at", "data_freshness",
))
SOURCE_FIELDS = frozenset(("site", "service", "floor", "content_type", "content_id"))
ENTITY_FIELDS = frozenset(("id", "name"))
IMAGE_FIELDS = frozenset(("large", "list", "small"))


@dataclass(frozen=True)
class ProjectionCandidateResult:
    version: str
    status: str
    structure_valid: bool
    exact_field_allowlist: bool
    field_rights_confirmed: bool
    publication_allowed: bool
    affiliate_activation_allowed: bool
    sitemap_change_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(valid: bool, reasons: tuple[str, ...]) -> ProjectionCandidateResult:
    return ProjectionCandidateResult(
        VERSION,
        READY if valid else FAIL_CLOSED,
        valid,
        valid,
        False,
        False,
        False,
        False,
        False,
        reasons,
    )


def _exact_mapping(value: Any, fields: frozenset[str]) -> bool:
    return isinstance(value, dict) and frozenset(value) == fields


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _entity_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(
            _exact_mapping(entry, ENTITY_FIELDS)
            and isinstance(entry["id"], (str, int))
            and not isinstance(entry["id"], bool)
            and bool(str(entry["id"]).strip())
            and _nonempty_string(entry["name"])
            for entry in value
        )
    )


def _safe_https_url(value: Any) -> bool:
    if not _nonempty_string(value):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _money(value: Any, optional: bool = False) -> bool:
    return (optional and value is None) or (
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
    )


def assess(candidate: Any) -> ProjectionCandidateResult:
    if not _exact_mapping(candidate, TOP_LEVEL_FIELDS):
        return _result(False, ("PROJECTION_FIELD_ALLOWLIST_MISMATCH",))
    source = candidate["source"]
    if not _exact_mapping(source, SOURCE_FIELDS):
        return _result(False, ("SOURCE_NAMESPACE_INVALID",))
    if (
        candidate["projection_version"] != VERSION
        or source["content_type"] not in CONTENT_TYPES
        or not all(_nonempty_string(source[key]) for key in SOURCE_FIELDS)
        or not isinstance(candidate["public_id"], str)
        or re.fullmatch(r"djn_[0-9a-f]{24}", candidate["public_id"]) is None
    ):
        return _result(False, ("PROJECTION_IDENTITY_INVALID",))
    if not (
        _nonempty_string(candidate["title"])
        and _nonempty_string(candidate["release_date_raw"])
        and _money(candidate["current_price"])
        and _money(candidate["list_price"], optional=True)
        and _money(candidate["discount_amount"], optional=True)
        and (
            candidate["discount_rate"] is None
            or isinstance(candidate["discount_rate"], (int, float))
            and not isinstance(candidate["discount_rate"], bool)
            and 0 <= candidate["discount_rate"] <= 100
        )
    ):
        return _result(False, ("PROJECTION_CORE_FIELD_INVALID",))
    if not (
        _entity_list(candidate["makers"])
        and len(candidate["makers"]) > 0
        and _entity_list(candidate["series"])
        and _entity_list(candidate["genres"])
        and len(candidate["genres"]) > 0
    ):
        return _result(False, ("PROJECTION_ENTITY_REFERENCE_INVALID",))
    if not (
        _exact_mapping(candidate["image"], IMAGE_FIELDS)
        and all(value is None or _safe_https_url(value) for value in candidate["image"].values())
        and any(_safe_https_url(value) for value in candidate["image"].values())
        and _safe_https_url(candidate["source_product_url"])
        and _nonempty_string(candidate["observed_at"])
        and candidate["data_freshness"] in {"CURRENT", "STALE"}
    ):
        return _result(False, ("PROJECTION_SOURCE_FACT_INVALID",))
    return _result(True, (
        "STRUCTURE_ONLY_CANDIDATE_VALIDATED",
        "FIELD_RIGHTS_REVIEW_REQUIRED",
        "PUBLICATION_REMAINS_CLOSED",
    ))
