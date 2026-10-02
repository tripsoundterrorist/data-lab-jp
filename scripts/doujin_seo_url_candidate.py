"""Pure, non-publishing SEO/URL candidate policy for future doujin items."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


VERSION = "0.1"
ORIGIN = "https://datalabx.jp"
PATH_PATTERN = "/doujin/items/{public_id}"
PUBLIC_ID = re.compile(r"djn_[0-9a-f]{24}\Z")
CONTENT_TYPES = frozenset({"doujin", "doujin_bl", "doujin_tl"})


@dataclass(frozen=True)
class DoujinSeoUrlDecision:
    version: str
    status: str
    path_pattern: str
    route_contract_valid: bool
    canonical_candidate: bool
    index_candidate: bool
    sitemap_candidate: bool
    noindex_required: bool
    entity_page_candidate: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str, *, route_valid: bool = False) -> DoujinSeoUrlDecision:
    return DoujinSeoUrlDecision(
        VERSION, "NOINDEX_REVIEW_CANDIDATE" if route_valid else "FAIL_CLOSED",
        PATH_PATTERN, route_valid, False, False, False, True, False, False,
        (reason, "PUBLICATION_REMAINS_CLOSED"),
    )


def evaluate(
    *,
    public_id: Any,
    content_type: Any,
    canonical_origin: Any,
    structure_ready: Any,
    rights_confirmed: Any,
    lifecycle_confirmed: Any,
    compliance_approved: Any,
    unique_user_value_confirmed: Any,
    publication_approved: Any,
) -> DoujinSeoUrlDecision:
    if (
        not isinstance(public_id, str)
        or PUBLIC_ID.fullmatch(public_id) is None
        or content_type not in CONTENT_TYPES
        or canonical_origin != ORIGIN
    ):
        return _blocked("URL_CONTRACT_INVALID")
    flags = (
        structure_ready, rights_confirmed, lifecycle_confirmed,
        compliance_approved, unique_user_value_confirmed, publication_approved,
    )
    if any(type(value) is not bool for value in flags):
        return _blocked("GATE_INPUT_INVALID", route_valid=True)
    if not all(flags):
        return _blocked("PUBLICATION_GATES_INCOMPLETE", route_valid=True)
    return DoujinSeoUrlDecision(
        VERSION, "SEO_REVIEW_CANDIDATE", PATH_PATTERN, True, True, True, True,
        False, False, False,
        (
            "ITEM_URL_CANONICAL_CANDIDATE_ONLY",
            "ENTITY_PAGES_REQUIRE_SEPARATE_VALUE_REVIEW",
            "PRODUCTION_WRITE_REQUIRES_SEPARATE_APPROVAL",
        ),
    )
