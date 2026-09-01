"""Pure bounded metrics for already-sanitized MOCK notification results."""

from __future__ import annotations

from dataclasses import dataclass
import re

import unattended_runtime as runtime


METRICS_VERSION = "0.1"
MAX_RESULTS = 10_000
_REASON = re.compile(r"[A-Z0-9_]{1,64}\Z")
_SUPPRESSION_STATUSES = frozenset({
    "DUPLICATE_EVENT_SUPPRESSED", "NOTIFICATION_SUPPRESSED",
    "NOTIFICATION_DUPLICATE_SUPPRESSED",
})


@dataclass(frozen=True)
class NotificationSuppressionMetrics:
    metrics_version: str
    status: str
    sample_count: int | None
    delivered_count: int | None
    suppressed_count: int | None
    reminder_count: int | None
    failed_safe_count: int | None
    emergency_blocked_count: int | None
    reason_codes: tuple[str, ...]


def _blocked(*reasons: str) -> NotificationSuppressionMetrics:
    return NotificationSuppressionMetrics(
        METRICS_VERSION, "METRICS_BLOCKED", None, None, None, None, None,
        None, tuple(reasons),
    )


def _valid_common(value: object) -> bool:
    if not isinstance(value, runtime.RuntimeResult):
        return False
    if (value.runtime_version != runtime.RUNTIME_VERSION or
            value.runtime_mode != "MOCK_RUNTIME" or
            value.event_type not in
            (runtime.AUTO_NOTIFY_EVENTS | runtime.SUPPRESSED_EVENTS)):
        return False
    if any(type(getattr(value, field)) is not bool for field in (
        "notification_selected", "notification_suppressed",
        "delivery_attempted", "delivery_succeeded", "approval_required",
        "emergency_blocked",
    )):
        return False
    if value.approval_required != (value.event_type == "JOB_WAITING_APPROVAL"):
        return False
    return (
        type(value.reason_codes) is tuple and bool(value.reason_codes) and
        all(type(reason) is str and _REASON.fullmatch(reason) is not None
            for reason in value.reason_codes)
    )


def _classification(value: object) -> str | None:
    if not _valid_common(value):
        return None
    assert isinstance(value, runtime.RuntimeResult)
    reminder = "INCIDENT_REMINDER_SELECTED" in value.reason_codes
    if value.runtime_status == "NOTIFICATION_DELIVERED":
        if (value.event_type in runtime.AUTO_NOTIFY_EVENTS and
                value.event_type != "CRITICAL_STOP" and
                (not reminder or value.event_type == "JOB_WAITING_APPROVAL") and
                value.notification_selected is True and
                value.notification_suppressed is False and
                value.delivery_attempted is True and
                value.delivery_succeeded is True and
                value.emergency_blocked is False):
            return "REMINDER" if reminder else "DELIVERED"
        return None
    if value.runtime_status in _SUPPRESSION_STATUSES:
        if (reminder or value.notification_suppressed is not True or
                value.delivery_attempted is not False or
                value.delivery_succeeded is not False or
                value.emergency_blocked is not False):
            return None
        if (value.runtime_status == "NOTIFICATION_SUPPRESSED" and
                value.event_type not in runtime.SUPPRESSED_EVENTS):
            return None
        if (value.runtime_status == "NOTIFICATION_DUPLICATE_SUPPRESSED" and
                value.event_type not in runtime.AUTO_NOTIFY_EVENTS):
            return None
        expected_selected = value.runtime_status == \
            "NOTIFICATION_DUPLICATE_SUPPRESSED"
        return "SUPPRESSED" if value.notification_selected is \
            expected_selected else None
    if value.runtime_status == "NOTIFICATION_FAILED_SAFE":
        if (value.event_type not in runtime.AUTO_NOTIFY_EVENTS or reminder or
                value.delivery_succeeded is not False or
                value.notification_suppressed is not False):
            return None
        return "FAILED_SAFE"
    if value.runtime_status == "EMERGENCY_SEND_BLOCKED":
        if (value.event_type != "CRITICAL_STOP" or reminder or
                value.notification_selected is not True or
                value.notification_suppressed is not False or
                value.delivery_succeeded is not False or
                value.emergency_blocked is not True):
            return None
        return "EMERGENCY_BLOCKED"
    return None


def summarize(results: object) -> NotificationSuppressionMetrics:
    """Aggregate no payload, timestamps, identities, text, or arbitrary reason."""
    if type(results) is not list or len(results) > MAX_RESULTS:
        return _blocked("NOTIFICATION_METRICS_INPUT_INVALID")
    classifications = [_classification(value) for value in results]
    if any(value is None for value in classifications):
        return _blocked("NOTIFICATION_METRICS_RESULT_INVALID")
    return NotificationSuppressionMetrics(
        METRICS_VERSION, "METRICS_READY", len(classifications),
        classifications.count("DELIVERED") + classifications.count("REMINDER"),
        classifications.count("SUPPRESSED"),
        classifications.count("REMINDER"),
        classifications.count("FAILED_SAFE"),
        classifications.count("EMERGENCY_BLOCKED"),
        ("NOTIFICATION_SUPPRESSION_METRICS_AGGREGATED",),
    )


__all__ = [
    "MAX_RESULTS", "METRICS_VERSION", "NotificationSuppressionMetrics",
    "summarize",
]
