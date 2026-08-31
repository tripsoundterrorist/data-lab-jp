"""Pure freshness contract for supplied development usage evidence."""

from __future__ import annotations

from dataclasses import dataclass

import development_usage_protection_permit as usage_core


CONTRACT_VERSION = "0.1"
SNAPSHOT_VERSION = "0.1"
TRUSTED_SOURCE = "USER_CONFIRMED"
MAX_AGE_SECONDS = 300


@dataclass(frozen=True)
class UsageEvidenceSnapshot:
    snapshot_version: str
    source: str
    observed_at_epoch_s: int
    five_hour_remaining_pct: int | None
    weekly_remaining_pct: int | None
    task_size: str
    operational_reserve_protected: bool


@dataclass(frozen=True)
class UsageFreshnessDecision:
    contract_version: str
    status: str
    evidence: usage_core.UsageProtectionEvidence | None
    checkpoint_required: bool
    reason_codes: tuple[str, ...]


def _decision(status: str,
              evidence: usage_core.UsageProtectionEvidence | None,
              checkpoint: bool, *reasons: str) -> UsageFreshnessDecision:
    return UsageFreshnessDecision(
        CONTRACT_VERSION, status, evidence, checkpoint, tuple(reasons)
    )


def evaluate(snapshot: object, *, evaluated_at_epoch_s: object
             ) -> UsageFreshnessDecision:
    """Validate supplied time evidence without reading a system clock."""
    if not isinstance(snapshot, UsageEvidenceSnapshot):
        return _decision(
            "SNAPSHOT_REJECTED", None, True, "USAGE_SNAPSHOT_TYPE_INVALID"
        )
    if (snapshot.snapshot_version != SNAPSHOT_VERSION or
            snapshot.source != TRUSTED_SOURCE):
        return _decision(
            "SNAPSHOT_REJECTED", None, True,
            "USAGE_SNAPSHOT_IDENTITY_INVALID",
        )
    if (type(snapshot.observed_at_epoch_s) is not int or
            snapshot.observed_at_epoch_s < 0 or
            type(evaluated_at_epoch_s) is not int or
            evaluated_at_epoch_s < 0):
        return _decision(
            "SNAPSHOT_REJECTED", None, True,
            "USAGE_SNAPSHOT_TIMESTAMP_INVALID",
        )
    age = evaluated_at_epoch_s - snapshot.observed_at_epoch_s
    if age < 0:
        return _decision(
            "SNAPSHOT_REJECTED", None, True,
            "USAGE_SNAPSHOT_FROM_FUTURE",
        )
    if age > MAX_AGE_SECONDS:
        return _decision(
            "SNAPSHOT_STALE", None, True, "USAGE_SNAPSHOT_STALE"
        )

    evidence = usage_core.UsageProtectionEvidence(
        snapshot.five_hour_remaining_pct,
        snapshot.weekly_remaining_pct,
        snapshot.task_size,
        snapshot.operational_reserve_protected,
    )
    return _decision(
        "SNAPSHOT_FRESH", evidence, False, "USAGE_SNAPSHOT_FRESH"
    )


__all__ = [
    "CONTRACT_VERSION", "MAX_AGE_SECONDS", "SNAPSHOT_VERSION",
    "TRUSTED_SOURCE",
    "UsageEvidenceSnapshot", "UsageFreshnessDecision", "evaluate",
]
