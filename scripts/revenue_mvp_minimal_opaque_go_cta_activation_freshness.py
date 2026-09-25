"""Activation-time freshness check for the exact Compliance-approved CTA artifact."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import revenue_mvp_minimal_opaque_go_cta_activation_review as activation_review
import revenue_mvp_minimal_opaque_go_cta_artifact_preflight as artifact_preflight


VERSION = "0.1-candidate"
FRESH = "EXACT_CTA_ARTIFACT_FRESH_FOR_ACTIVATION_REVIEW"
BLOCKED = "EXACT_CTA_ARTIFACT_FRESHNESS_BLOCKED"
MAX_AGE = timedelta(hours=24)


@dataclass(frozen=True)
class ActivationFreshnessResult:
    version: str
    status: str
    artifact_sha256: str | None
    observed_at: str | None
    freshness_confirmed: bool
    ready_to_request_explicit_activation_review: bool
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    d1_write_allowed: bool = False
    deployment_allowed: bool = False
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> ActivationFreshnessResult:
    return ActivationFreshnessResult(
        VERSION, BLOCKED, None, None, False, False,
        reason_codes=(reason,),
    )


class _TimeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "time":
            value = dict(attrs).get("datetime")
            if value is not None:
                self.values.append(value)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is None:
        raise ValueError("naive timestamp")
    return parsed.astimezone(timezone.utc)


def review(artifact: bytes, *, evaluated_at: Any) -> ActivationFreshnessResult:
    """Revalidate the exact artifact and its observation age; perform no action."""

    try:
        if type(evaluated_at) is not datetime or evaluated_at.tzinfo is None:
            return _blocked("EVALUATION_TIME_INVALID")
        digest = activation_review.COMPLIANCE_APPROVED_ARTIFACT_SHA256
        structural = artifact_preflight.review(artifact, digest)
        if (
            structural.status != artifact_preflight.PASS
            or structural.artifact_sha256 != digest
            or not structural.eligible_for_manual_activation_review
        ):
            return _blocked("EXACT_ARTIFACT_PREFLIGHT_REQUIRED")
        parser = _TimeParser()
        parser.feed(artifact.decode("utf-8"))
        parser.close()
        if len(parser.values) != 1:
            return _blocked("EXACT_OBSERVATION_TIME_REQUIRED")
        observed = _timestamp(parser.values[0])
        now = evaluated_at.astimezone(timezone.utc)
        if not timedelta(0) <= now - observed <= MAX_AGE:
            return _blocked("ARTIFACT_OBSERVATION_STALE")
        return ActivationFreshnessResult(
            VERSION, FRESH, digest, parser.values[0], True, True,
            reason_codes=(
                "EXACT_COMPLIANCE_APPROVED_ARTIFACT_REVALIDATED",
                "OBSERVATION_FRESH_AT_REVIEW_TIME",
                "EXPLICIT_USER_ACTIVATION_APPROVAL_REQUIRED",
            ),
        )
    except (UnicodeDecodeError, ValueError):
        return _blocked("ARTIFACT_FRESHNESS_PARSE_FAILED")
    except Exception:
        return _blocked("ARTIFACT_FRESHNESS_REVIEW_ERROR")


__all__ = [
    "ActivationFreshnessResult", "BLOCKED", "FRESH", "MAX_AGE", "VERSION", "review",
]
