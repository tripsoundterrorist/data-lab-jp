"""Pure candidate policy for doujin observation-time and freshness wording."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import category_collection_health as collection_health


VERSION = "0.1"
CURRENT = "CURRENT"
STALE = "STALE"
FAIL_CLOSED = "FAIL_CLOSED"
OBSERVATION_LABEL = "DATA LAB確認日時"


@dataclass(frozen=True)
class DoujinObservationFreshnessDecision:
    version: str
    status: str
    observation_label: str | None
    display_candidate: bool
    official_update_claim_allowed: bool
    realtime_claim_allowed: bool
    publication_allowed: bool
    gate_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str, *, stale: bool = False) -> DoujinObservationFreshnessDecision:
    return DoujinObservationFreshnessDecision(
        VERSION, STALE if stale else FAIL_CLOSED,
        OBSERVATION_LABEL if stale else None, False, False, False, False, False,
        (reason, "PUBLICATION_REMAINS_CLOSED"),
    )


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp type")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def evaluate(*, observed_at: Any, evaluated_at: Any) -> DoujinObservationFreshnessDecision:
    try:
        observed = _timestamp(observed_at)
        evaluated = _timestamp(evaluated_at)
        age = (evaluated - observed).total_seconds()
        if age < 0:
            return _blocked("OBSERVATION_IN_FUTURE")
        if age > collection_health.MAX_AGE_SECONDS:
            return _blocked("OBSERVATION_STALE", stale=True)
        return DoujinObservationFreshnessDecision(
            VERSION, CURRENT, OBSERVATION_LABEL, True, False, False, False,
            False,
            (
                "DATA_LAB_OBSERVATION_LABEL_REQUIRED",
                "OFFICIAL_UPDATE_AND_REALTIME_CLAIMS_FORBIDDEN",
                "STRUCTURE_CANDIDATE_ONLY",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except (TypeError, ValueError, OverflowError):
        return _blocked("TIMESTAMP_INVALID")
    except Exception:
        return _blocked("FRESHNESS_POLICY_ERROR")
