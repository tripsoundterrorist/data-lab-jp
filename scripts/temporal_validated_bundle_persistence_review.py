"""Pure review of the test-only validated-bundle persistence connection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VERSION = "0.1-candidate"
AREAS = (
    "EXACT_VALIDATED_BUNDLE", "TEST_ONLY_STORE", "BOUNDED_FOUR_STATE_WRITE",
    "FAIL_CLOSED_DOWNSTREAM", "SAFE_RESULT", "ACTIVE_FLOW_SEPARATION",
)


@dataclass(frozen=True)
class Evidence:
    version: str
    exact_validated_bundle: bool
    test_only_store: bool
    bounded_four_state_write: bool
    fail_closed_downstream: bool
    safe_result: bool
    active_flow_separation: bool
    approval_granted: bool


@dataclass(frozen=True)
class Review:
    version: str
    status: str
    unmet_areas: tuple[str, ...]
    active_connection_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    reason_codes: tuple[str, ...]


def review(value: Any) -> Review:
    try:
        if type(value) is not Evidence or value.version != VERSION:
            return Review(VERSION, "REVIEW_BLOCKED", AREAS, False, False, False,
                          ("EVIDENCE_INVALID",))
        checks = (value.exact_validated_bundle, value.test_only_store,
                  value.bounded_four_state_write, value.fail_closed_downstream,
                  value.safe_result, value.active_flow_separation)
        if any(type(item) is not bool for item in (*checks, value.approval_granted)):
            return Review(VERSION, "REVIEW_BLOCKED", AREAS, False, False, False,
                          ("EVIDENCE_INVALID",))
        if value.approval_granted:
            return Review(VERSION, "REVIEW_BLOCKED", AREAS, False, False, False,
                          ("APPROVAL_INPUT_NOT_ACCEPTED",))
        unmet = tuple(area for area, complete in zip(AREAS, checks) if not complete)
        if unmet:
            return Review(VERSION, "REVIEW_BLOCKED", unmet, False, False, False,
                          ("REVIEW_EVIDENCE_INCOMPLETE",))
        return Review(VERSION, "REVIEW_READY_FOR_EXPLICIT_APPROVAL", (),
                      False, False, False,
                      ("ISOLATED_CONNECTION_EVIDENCE_REVIEWED",
                       "ACTIVE_CONNECTION_APPROVAL_REQUIRED"))
    except Exception:
        return Review(VERSION, "REVIEW_BLOCKED", AREAS, False, False, False,
                      ("REVIEW_ERROR",))


__all__ = ["AREAS", "Evidence", "Review", "VERSION", "review"]
