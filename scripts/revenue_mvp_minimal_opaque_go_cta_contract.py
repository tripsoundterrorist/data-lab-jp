"""Pure review contract for a separate minimal opaque `/go/` CTA scope."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


VERSION = "0.1-candidate"
READY = "MINIMAL_OPAQUE_GO_CTA_IMPLEMENTATION_REVIEW_CANDIDATE"
BLOCKED = "MINIMAL_OPAQUE_GO_CTA_BLOCKED"
DISCLOSURE = "【PR】FANZAで確認"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
FIELDS = frozenset({
    "contract_version", "public_id", "cta_href", "disclosure_text",
    "disclosure_proximate", "affiliate_url_exposed",
    "server_side_lookup_required", "rate_limit_required",
    "publication_scope_expanded", "exact_unordered_scope_unchanged",
})


@dataclass(frozen=True)
class MinimalOpaqueGoCtaReview:
    version: str
    status: str
    eligible_for_implementation_review: bool
    public_id_accepted: bool
    same_origin_route_accepted: bool
    disclosure_accepted: bool
    publication_allowed: bool
    production_activation_allowed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    deployment_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> MinimalOpaqueGoCtaReview:
    return MinimalOpaqueGoCtaReview(
        VERSION, BLOCKED, False, False, False, False,
        False, False, False, False, False, (reason,),
    )


def review(value: Any) -> MinimalOpaqueGoCtaReview:
    """Validate only the opaque route and disclosure; never authorize activation."""
    try:
        if type(value) is not dict or set(value) != FIELDS:
            return _blocked("INPUT_CONTRACT_INVALID")
        if value["contract_version"] != VERSION:
            return _blocked("CONTRACT_VERSION_INVALID")
        public_id = value["public_id"]
        href = value["cta_href"]
        if type(public_id) is not str or PUBLIC_ID.fullmatch(public_id) is None:
            return _blocked("OPAQUE_PUBLIC_ID_INVALID")
        if type(href) is not str or href != f"/go/{public_id}":
            return _blocked("SAME_ORIGIN_ROUTE_INVALID")
        if (
            value["disclosure_text"] != DISCLOSURE
            or value["disclosure_proximate"] is not True
        ):
            return _blocked("PR_DISCLOSURE_INVALID")
        if value["affiliate_url_exposed"] is not False:
            return _blocked("AFFILIATE_URL_EXPOSURE_FORBIDDEN")
        if (
            value["server_side_lookup_required"] is not True
            or value["rate_limit_required"] is not True
        ):
            return _blocked("SERVER_SIDE_SAFETY_REQUIRED")
        if (
            value["publication_scope_expanded"] is not True
            or value["exact_unordered_scope_unchanged"] is not True
        ):
            return _blocked("SEPARATE_SCOPE_BOUNDARY_REQUIRED")
        return MinimalOpaqueGoCtaReview(
            VERSION, READY, True, True, True, True,
            False, False, False, False, False,
            (
                "SEPARATE_MINIMAL_CTA_SCOPE_REVIEWED",
                "OPAQUE_SAME_ORIGIN_ROUTE_ONLY",
                "PROXIMATE_PR_DISCLOSURE_REQUIRED",
                "EXPLICIT_ACTIVATION_REVIEW_REQUIRED",
            ),
        )
    except Exception:
        return _blocked("MINIMAL_CTA_REVIEW_ERROR")


__all__ = ["BLOCKED", "DISCLOSURE", "READY", "VERSION",
           "MinimalOpaqueGoCtaReview", "review"]
