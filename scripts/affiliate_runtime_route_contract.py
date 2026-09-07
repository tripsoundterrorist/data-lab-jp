"""Pure, non-deploying HTTP boundary for an affiliate runtime route."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


ROUTE_VERSION = "0.1"
ROUTE_CANDIDATE = "ROUTE_CANDIDATE"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"

PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
ROUTE = re.compile(r"/go/(itm_[0-9a-f]{24})\Z")
ALLOWED_METHODS = frozenset({"GET", "HEAD"})
SAFE_HEADERS = (
    ("Cache-Control", "no-store, max-age=0"),
    ("Pragma", "no-cache"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Robots-Tag", "noindex, nofollow, noarchive"),
)


@dataclass(frozen=True)
class AffiliateRouteResult:
    route_version: str
    status: str
    response_status: int
    pipeline_invocation_candidate: bool
    request_body_accepted: bool
    response_body_allowed: bool
    redirect_location_present: bool
    response_headers: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["response_headers"] = [list(item) for item in self.response_headers]
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    response_status: int,
    reasons: tuple[str, ...],
    *,
    pipeline_candidate: bool = False,
) -> AffiliateRouteResult:
    return AffiliateRouteResult(
        ROUTE_VERSION,
        status,
        response_status,
        pipeline_candidate,
        False,
        False,
        False,
        SAFE_HEADERS,
        reasons,
    )


def assess_route_request(
    *,
    route_version: Any,
    method: Any,
    path: Any,
    request_body_present: Any,
    official_answer_candidate: Any,
    publication_gate_overall_eligible: Any,
    runtime_chain_connected: Any,
    rate_limit_allowed: Any,
    pr_disclosure_available: Any,
) -> AffiliateRouteResult:
    """Validate safe request facts; never invoke a pipeline or expose a URL."""

    try:
        boolean_values = (
            request_body_present,
            official_answer_candidate,
            publication_gate_overall_eligible,
            runtime_chain_connected,
            rate_limit_allowed,
            pr_disclosure_available,
        )
        if route_version != ROUTE_VERSION:
            return _result(FAIL_CLOSED, 404, ("UNSUPPORTED_ROUTE_VERSION",))
        if not isinstance(method, str) or not isinstance(path, str):
            return _result(FAIL_CLOSED, 404, ("INVALID_REQUEST_SHAPE",))
        if not all(type(value) is bool for value in boolean_values):
            return _result(FAIL_CLOSED, 404, ("INVALID_GUARD_SHAPE",))
        if method not in ALLOWED_METHODS:
            return _result(BLOCKED, 405, ("METHOD_NOT_ALLOWED",))
        match = ROUTE.fullmatch(path)
        if match is None or PUBLIC_ID.fullmatch(match.group(1)) is None:
            return _result(BLOCKED, 404, ("ROUTE_NOT_FOUND",))
        if request_body_present:
            return _result(BLOCKED, 400, ("REQUEST_BODY_FORBIDDEN",))
        if not rate_limit_allowed:
            return _result(BLOCKED, 429, ("RATE_LIMIT_BLOCKED",))

        blockers = []
        if not official_answer_candidate:
            blockers.append("OFFICIAL_ANSWER_GATE_CLOSED")
        if not publication_gate_overall_eligible:
            blockers.append("PUBLICATION_GATE_CLOSED")
        if not runtime_chain_connected:
            blockers.append("RUNTIME_CHAIN_NOT_CONNECTED")
        if not pr_disclosure_available:
            blockers.append("PR_DISCLOSURE_NOT_READY")
        if blockers:
            return _result(BLOCKED, 404, tuple(blockers))

        return _result(
            ROUTE_CANDIDATE,
            302,
            ("ROUTE_REQUEST_VALIDATED",),
            pipeline_candidate=True,
        )
    except Exception:
        return _result(FAIL_CLOSED, 404, ("ROUTE_CONTRACT_INTERNAL_ERROR",))


__all__ = [
    "AffiliateRouteResult",
    "BLOCKED",
    "FAIL_CLOSED",
    "ROUTE_CANDIDATE",
    "ROUTE_VERSION",
    "SAFE_HEADERS",
    "assess_route_request",
]
