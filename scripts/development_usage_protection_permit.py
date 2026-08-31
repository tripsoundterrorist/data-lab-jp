"""Pure fail-closed permit for DATA LAB development usage protection."""

from __future__ import annotations

from dataclasses import dataclass


PERMIT_VERSION = "0.1"
TASK_SIZES = frozenset({"SMALL", "LARGE"})


@dataclass(frozen=True)
class UsageProtectionEvidence:
    five_hour_remaining_pct: int | None
    weekly_remaining_pct: int | None
    task_size: str
    operational_reserve_protected: bool


@dataclass(frozen=True)
class UsageProtectionDecision:
    permit_version: str
    status: str
    new_task_allowed: bool
    checkpoint_required: bool
    reason_codes: tuple[str, ...]


def _decision(status: str, allowed: bool, checkpoint: bool,
              *reasons: str) -> UsageProtectionDecision:
    return UsageProtectionDecision(
        PERMIT_VERSION, status, allowed, checkpoint, tuple(reasons)
    )


def _valid_percentage(value: object) -> bool:
    return type(value) is int and 0 <= value <= 100


def evaluate(value: object) -> UsageProtectionDecision:
    if not isinstance(value, UsageProtectionEvidence):
        return _decision("BLOCKED", False, False, "USAGE_EVIDENCE_INVALID")
    if value.task_size not in TASK_SIZES:
        return _decision("BLOCKED", False, False, "TASK_SIZE_INVALID")
    if type(value.operational_reserve_protected) is not bool:
        return _decision("BLOCKED", False, False,
                         "OPERATIONAL_RESERVE_POLICY_INVALID")
    if value.five_hour_remaining_pct is None or \
            value.weekly_remaining_pct is None:
        return _decision("BLOCKED", False, True,
                         "USAGE_REMAINING_UNKNOWN")
    if not _valid_percentage(value.five_hour_remaining_pct) or \
            not _valid_percentage(value.weekly_remaining_pct):
        return _decision("BLOCKED", False, False,
                         "USAGE_PERCENTAGE_INVALID")
    if not value.operational_reserve_protected:
        return _decision("BLOCKED", False, True,
                         "OPERATIONAL_RESERVE_NOT_PROTECTED")

    stop_reasons = []
    if value.five_hour_remaining_pct <= 10:
        stop_reasons.append("FIVE_HOUR_STOP_THRESHOLD")
    if value.weekly_remaining_pct <= 15:
        stop_reasons.append("WEEKLY_STOP_THRESHOLD")
    if stop_reasons:
        return _decision("CHECKPOINT_AND_STOP", False, True, *stop_reasons)

    if value.task_size == "LARGE":
        large_reasons = []
        if value.five_hour_remaining_pct <= 15:
            large_reasons.append("FIVE_HOUR_LARGE_TASK_STOP")
        if value.weekly_remaining_pct <= 20:
            large_reasons.append("WEEKLY_LARGE_TASK_STOP")
        if large_reasons:
            return _decision("LARGE_TASK_BLOCKED", False, False,
                             *large_reasons)

    return _decision("PERMITTED", True, False,
                     "USAGE_AND_OPERATIONAL_RESERVE_AVAILABLE")


__all__ = [
    "PERMIT_VERSION", "TASK_SIZES", "UsageProtectionDecision",
    "UsageProtectionEvidence", "evaluate",
]
