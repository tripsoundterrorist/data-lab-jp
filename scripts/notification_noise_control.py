"""Pure fail-closed duplicate-notification policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re


POLICY_VERSION = "0.1"
EVENT_KEY = re.compile(r"[0-9a-f]{64}\Z")

IMMEDIATE_EVENTS = frozenset({
    "JOB_WAITING_APPROVAL", "JOB_FAILED_SAFE", "QUEUE_BLOCKED",
})
NORMAL_EVENTS = frozenset({"JOB_COMPLETED"})
CRITICAL_EVENTS = frozenset({"CRITICAL_STOP"})
ALLOWED_EVENTS = IMMEDIATE_EVENTS | NORMAL_EVENTS | CRITICAL_EVENTS

REMINDER_WINDOWS = {
    "JOB_WAITING_APPROVAL": timedelta(minutes=30),
    "JOB_FAILED_SAFE": timedelta(hours=1),
    "QUEUE_BLOCKED": timedelta(hours=1),
}


@dataclass(frozen=True)
class NotificationNoiseEvidence:
    event_type: str
    event_key: str
    occurred_at: str
    last_delivered_event_key: str | None = None
    last_delivered_at: str | None = None


@dataclass(frozen=True)
class NotificationNoiseDecision:
    policy_version: str
    status: str
    action: str
    delivery_allowed: bool
    reminder: bool
    reason_codes: tuple[str, ...]


def _decision(status: str, action: str, allowed: bool, reminder: bool,
              *reasons: str) -> NotificationNoiseDecision:
    return NotificationNoiseDecision(
        POLICY_VERSION, status, action, allowed, reminder, tuple(reasons)
    )


def _parse_time(value: object) -> datetime | None:
    if type(value) is not str or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def evaluate(value: object) -> NotificationNoiseDecision:
    if not isinstance(value, NotificationNoiseEvidence):
        return _decision("INVALID_INPUT", "NONE", False, False,
                         "NOISE_EVIDENCE_TYPE_INVALID")
    if value.event_type not in ALLOWED_EVENTS:
        return _decision("INVALID_INPUT", "NONE", False, False,
                         "EVENT_TYPE_INVALID")
    if type(value.event_key) is not str or EVENT_KEY.fullmatch(value.event_key) is None:
        return _decision("INVALID_INPUT", "NONE", False, False,
                         "EVENT_KEY_INVALID")
    occurred = _parse_time(value.occurred_at)
    if occurred is None:
        return _decision("INVALID_INPUT", "NONE", False, False,
                         "OCCURRED_AT_INVALID")

    no_previous = (value.last_delivered_event_key is None and
                   value.last_delivered_at is None)
    if not no_previous:
        if (type(value.last_delivered_event_key) is not str or
                EVENT_KEY.fullmatch(value.last_delivered_event_key) is None):
            return _decision("INVALID_INPUT", "NONE", False, False,
                             "LAST_EVENT_KEY_INVALID")
        last = _parse_time(value.last_delivered_at)
        if last is None:
            return _decision("INVALID_INPUT", "NONE", False, False,
                             "LAST_DELIVERED_AT_INVALID")
        if occurred < last:
            return _decision("INVALID_INPUT", "NONE", False, False,
                             "EVENT_TIME_REGRESSION")
    else:
        last = None

    if value.event_type in CRITICAL_EVENTS:
        return _decision("CRITICAL_BOUNDARY_PRESERVED", "PRESERVE_CRITICAL", False,
                         False, "CRITICAL_SEND_POLICY_UNCHANGED")

    duplicate = (not no_previous and
                 value.event_key == value.last_delivered_event_key)
    if not duplicate:
        action = "DELIVER_IMMEDIATE" if value.event_type in IMMEDIATE_EVENTS \
            else "DELIVER_NORMAL"
        return _decision("DELIVERY_SELECTED", action, True, False,
                         "FIRST_OR_DISTINCT_EVENT")

    if value.event_type in NORMAL_EVENTS:
        return _decision("DUPLICATE_SUPPRESSED", "SUPPRESS", False, False,
                         "COMPLETION_DUPLICATE")

    assert last is not None
    if occurred - last < REMINDER_WINDOWS[value.event_type]:
        return _decision("DUPLICATE_SUPPRESSED", "SUPPRESS", False, False,
                         "REMINDER_WINDOW_NOT_ELAPSED")
    return _decision("REMINDER_SELECTED", "DELIVER_IMMEDIATE", True, True,
                     "REMINDER_WINDOW_ELAPSED")


__all__ = [
    "NotificationNoiseDecision", "NotificationNoiseEvidence", "POLICY_VERSION",
    "REMINDER_WINDOWS", "evaluate",
]
