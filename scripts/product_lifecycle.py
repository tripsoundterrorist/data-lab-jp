from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re
from typing import Any, Mapping


class LifecycleState(str, Enum):
    OBSERVED = "OBSERVED"
    VERIFICATION_DUE = "VERIFICATION_DUE"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    CONFIRMED_AVAILABLE = "CONFIRMED_AVAILABLE"
    CONFIRMED_UNAVAILABLE = "CONFIRMED_UNAVAILABLE"
    VERIFICATION_ERROR = "VERIFICATION_ERROR"
    UNKNOWN = "UNKNOWN"


class VerificationResult(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "verification_error"
    PENDING = "verification_pending"


REASON_ORDER = (
    "NO_OBSERVATION",
    "NO_EXPLICIT_VERIFICATION",
    "OBSERVATION_STALE",
    "COLLECTOR_NON_OBSERVATION_NOT_AVAILABILITY_SIGNAL",
    "VERIFICATION_PENDING",
    "VERIFICATION_ERROR",
    "EXPLICIT_UNAVAILABLE",
    "VERIFICATION_EXPIRED",
    "INVALID_TIMESTAMP",
    "UNKNOWN_VERIFICATION_RESULT",
    "MALFORMED_VERIFICATION",
    "INVALID_POLICY",
    "INTERNAL_EVALUATION_ERROR",
)

PROVENANCE_FIELDS = frozenset(
    {
        "verification_source",
        "verified_at",
        "verification_result",
        "verification_reason",
        "source_status_code",
    }
)
SAFE_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
SAFE_SOURCE_STATUS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


@dataclass(frozen=True)
class LifecyclePolicy:
    observation_recency_window: timedelta
    verification_ttl: timedelta


@dataclass(frozen=True)
class VerificationProvenance:
    verification_source: str
    verified_at: datetime
    verification_result: VerificationResult
    verification_reason: str
    source_status_code: str | int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_source": self.verification_source,
            "verified_at": self.verified_at.isoformat().replace("+00:00", "Z"),
            "verification_result": self.verification_result.value,
            "verification_reason": self.verification_reason,
            "source_status_code": self.source_status_code,
        }


@dataclass(frozen=True)
class LifecycleEvaluation:
    state: LifecycleState
    lifecycle_eligible_for_publication: bool
    reasons: tuple[str, ...]
    last_observed_at: datetime | None
    verification: VerificationProvenance | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "lifecycle_eligible_for_publication": (
                self.lifecycle_eligible_for_publication
            ),
            "reasons": list(self.reasons),
            "last_observed_at": (
                self.last_observed_at.isoformat().replace("+00:00", "Z")
                if self.last_observed_at is not None
                else None
            ),
            "verification": (
                self.verification.to_dict()
                if self.verification is not None
                else None
            ),
        }


def ordered_reasons(reasons: set[str]) -> tuple[str, ...]:
    return tuple(code for code in REASON_ORDER if code in reasons)


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def valid_policy(policy: LifecyclePolicy) -> bool:
    return (
        isinstance(policy, LifecyclePolicy)
        and isinstance(policy.observation_recency_window, timedelta)
        and isinstance(policy.verification_ttl, timedelta)
        and policy.observation_recency_window > timedelta(0)
        and policy.verification_ttl > timedelta(0)
    )


def safe_code(value: Any) -> bool:
    return (
        isinstance(value, str)
        and SAFE_CODE_PATTERN.fullmatch(value) is not None
    )


def safe_source_status_code(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 999
    return (
        isinstance(value, str)
        and SAFE_SOURCE_STATUS_PATTERN.fullmatch(value) is not None
    )


def parse_verification(
    value: Mapping[str, Any], as_of: datetime, reasons: set[str]
) -> VerificationProvenance | None:
    if not isinstance(value, Mapping) or set(value) != PROVENANCE_FIELDS:
        reasons.add("MALFORMED_VERIFICATION")
        return None
    source = value.get("verification_source")
    reason = value.get("verification_reason")
    if not safe_code(source) or not safe_code(reason):
        reasons.add("MALFORMED_VERIFICATION")
        return None
    verified_at = parse_timestamp(value.get("verified_at"))
    if verified_at is None or verified_at > as_of:
        reasons.add("INVALID_TIMESTAMP")
        return None
    try:
        result = VerificationResult(value.get("verification_result"))
    except (TypeError, ValueError):
        reasons.add("UNKNOWN_VERIFICATION_RESULT")
        return None
    source_status_code = value.get("source_status_code")
    if not safe_source_status_code(source_status_code):
        reasons.add("MALFORMED_VERIFICATION")
        return None
    return VerificationProvenance(
        verification_source=source,
        verified_at=verified_at,
        verification_result=result,
        verification_reason=reason,
        source_status_code=source_status_code,
    )


def blocked(
    state: LifecycleState,
    reasons: set[str],
    last_observed_at: datetime | None,
    verification: VerificationProvenance | None,
) -> LifecycleEvaluation:
    return LifecycleEvaluation(
        state=state,
        lifecycle_eligible_for_publication=False,
        reasons=ordered_reasons(reasons),
        last_observed_at=last_observed_at,
        verification=verification,
    )


def evaluate(
    *,
    last_observed_at: str | None,
    verification: Mapping[str, Any] | None,
    as_of: datetime,
    policy: LifecyclePolicy,
) -> LifecycleEvaluation:
    reasons: set[str] = set()
    if as_of.tzinfo is None:
        return blocked(LifecycleState.UNKNOWN, {"INVALID_TIMESTAMP"}, None, None)
    normalized_as_of = as_of.astimezone(timezone.utc)
    if not valid_policy(policy):
        return blocked(LifecycleState.UNKNOWN, {"INVALID_POLICY"}, None, None)

    observed = None
    if last_observed_at is not None:
        observed = parse_timestamp(last_observed_at)
        if observed is None or observed > normalized_as_of:
            return blocked(LifecycleState.UNKNOWN, {"INVALID_TIMESTAMP"}, None, None)

    if verification is None:
        reasons.add("NO_EXPLICIT_VERIFICATION")
        if observed is None:
            reasons.add("NO_OBSERVATION")
            return blocked(LifecycleState.UNKNOWN, reasons, None, None)
        if normalized_as_of - observed <= policy.observation_recency_window:
            return blocked(LifecycleState.OBSERVED, reasons, observed, None)
        reasons.update(
            {
                "OBSERVATION_STALE",
                "COLLECTOR_NON_OBSERVATION_NOT_AVAILABILITY_SIGNAL",
            }
        )
        return blocked(LifecycleState.VERIFICATION_DUE, reasons, observed, None)

    provenance = parse_verification(verification, normalized_as_of, reasons)
    if provenance is None:
        return blocked(LifecycleState.UNKNOWN, reasons, observed, None)
    result = provenance.verification_result
    if result is VerificationResult.PENDING:
        reasons.add("VERIFICATION_PENDING")
        return blocked(
            LifecycleState.VERIFICATION_PENDING, reasons, observed, provenance
        )
    if result is VerificationResult.ERROR:
        reasons.add("VERIFICATION_ERROR")
        return blocked(LifecycleState.VERIFICATION_ERROR, reasons, observed, provenance)
    if normalized_as_of - provenance.verified_at > policy.verification_ttl:
        reasons.add("VERIFICATION_EXPIRED")
        return blocked(LifecycleState.VERIFICATION_DUE, reasons, observed, provenance)
    if result is VerificationResult.UNAVAILABLE:
        reasons.add("EXPLICIT_UNAVAILABLE")
        return blocked(
            LifecycleState.CONFIRMED_UNAVAILABLE, reasons, observed, provenance
        )
    return LifecycleEvaluation(
        state=LifecycleState.CONFIRMED_AVAILABLE,
        lifecycle_eligible_for_publication=True,
        reasons=(),
        last_observed_at=observed,
        verification=provenance,
    )


def evaluate_product_lifecycle(
    *,
    last_observed_at: str | None,
    verification: Mapping[str, Any] | None,
    as_of: datetime,
    policy: LifecyclePolicy,
) -> LifecycleEvaluation:
    try:
        return evaluate(
            last_observed_at=last_observed_at,
            verification=verification,
            as_of=as_of,
            policy=policy,
        )
    except Exception:
        return blocked(
            LifecycleState.UNKNOWN,
            {"INTERNAL_EVALUATION_ERROR"},
            None,
            None,
        )
