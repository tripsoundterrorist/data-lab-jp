"""Pure fail-closed adapter from queue safe events to Pushover-safe messages.

No network, environment, filesystem, persistence, or queue mutation occurs.
The result is a bounded message contract; it is not a Pushover API request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

import unattended_job_queue as queue


ADAPTER_VERSION = "0.1"
READY = "READY"
INVALID_INPUT = "INVALID_INPUT"
TITLE_LIMIT = 100
MESSAGE_LIMIT = 512
INPUT_FIELDS = frozenset({
    "event_version", "event_type", "job_id", "job_type", "severity", "state",
    "approval_required", "summary_code", "occurred_at",
})
OUTPUT_FIELDS = frozenset({
    "adapter_version", "notification_status", "pushover_priority",
    "emergency_candidate", "delivery_class", "title", "message",
    "approval_required", "reason_codes",
})
SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
UNSAFE_VALUE = re.compile(
    r"(?i)(?:https?|ftp|file)://|www\.|[a-z]:[\\/]|^/|^\\\\|"
    r"(?:api|affiliate)[_-]?id|credential|password|secret|token|"
    r"raw(?:_response|_exception)?|traceback|title|content_ids?|product_ids?|path"
)


@dataclass(frozen=True)
class PushoverNotification:
    adapter_version: str
    notification_status: str
    pushover_priority: int | None
    emergency_candidate: bool
    delivery_class: str | None
    title: str
    message: str
    approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


MAPPINGS = {
    "JOB_STARTED": (-1, "SUPPRESSIBLE", "DATA LAB — Job Started", "Job started safely."),
    "JOB_COMPLETED": (0, "NORMAL", "DATA LAB — Completed", "Job completed successfully."),
    "JOB_FAILED_SAFE": (1, "IMMEDIATE", "DATA LAB — Failed Safely", "Job stopped safely. No unsafe continuation was attempted."),
    "JOB_WAITING_APPROVAL": (1, "IMMEDIATE", "DATA LAB — Approval Required", "User approval is required before this job can continue."),
    "JOB_CHECKPOINTED": (0, "SUPPRESSIBLE", "DATA LAB — Checkpointed", "Job progress was checkpointed safely."),
    "JOB_SWITCHED": (0, "SUPPRESSIBLE", "DATA LAB — Job Switched", "Current job was paused and another eligible job was selected."),
    "QUEUE_IDLE": (-1, "SUPPRESSIBLE", "DATA LAB — Queue Idle", "No eligible job is currently available."),
    "QUEUE_BLOCKED": (1, "IMMEDIATE", "DATA LAB — Queue Blocked", "The queue stopped safely because no job can continue."),
    "CRITICAL_STOP": (2, "IMMEDIATE", "DATA LAB — Critical Stop", "Unattended execution stopped because a critical safety condition was detected."),
}


def _invalid(*reasons: str) -> PushoverNotification:
    return PushoverNotification(
        ADAPTER_VERSION, INVALID_INPUT, None, False, None, "", "", False,
        tuple(sorted(set(reasons))),
    )


def _event_dict(event: Any) -> Mapping[str, Any] | None:
    if isinstance(event, queue.NotificationEvent):
        return event.to_dict()
    return event if isinstance(event, Mapping) else None


def _valid_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _adapt(event: Any, adapter_version: Any) -> PushoverNotification:
    if adapter_version != ADAPTER_VERSION:
        return _invalid("ADAPTER_VERSION_UNSUPPORTED")
    values = _event_dict(event)
    if values is None:
        return _invalid("EVENT_CONTRACT_INVALID")
    if set(values) != INPUT_FIELDS:
        return _invalid("EVENT_SCHEMA_INVALID")
    if values["event_version"] != queue.EVENT_VERSION:
        return _invalid("EVENT_VERSION_UNSUPPORTED")
    event_type = values["event_type"]
    if event_type not in MAPPINGS:
        return _invalid("EVENT_TYPE_UNKNOWN")
    if values["severity"] not in queue.SEVERITIES:
        return _invalid("SEVERITY_UNKNOWN")
    if values["state"] not in queue.JOB_STATES:
        return _invalid("STATE_MALFORMED")
    if not isinstance(values["approval_required"], bool):
        return _invalid("APPROVAL_FLAG_MALFORMED")
    if values["approval_required"] != (event_type == "JOB_WAITING_APPROVAL"):
        return _invalid("APPROVAL_FLAG_CONTRADICTORY")
    if event_type == "CRITICAL_STOP" and values["severity"] != "CRITICAL":
        return _invalid("CRITICAL_SEVERITY_REQUIRED")
    if not isinstance(values["job_id"], str) or SAFE_TOKEN.fullmatch(values["job_id"]) is None:
        return _invalid("JOB_ID_INVALID")
    if not isinstance(values["job_type"], str) or SAFE_TOKEN.fullmatch(values["job_type"]) is None:
        return _invalid("JOB_TYPE_INVALID")
    if not isinstance(values["summary_code"], str) or SAFE_CODE.fullmatch(values["summary_code"]) is None:
        return _invalid("SUMMARY_CODE_INVALID")
    safe_values = (values["job_id"], values["job_type"], values["summary_code"])
    if any(UNSAFE_VALUE.search(value) for value in safe_values):
        return _invalid("UNSAFE_INPUT_CONTENT")
    if not _valid_time(values["occurred_at"]):
        return _invalid("OCCURRED_AT_INVALID")
    priority, delivery_class, title, message = MAPPINGS[event_type]
    if len(title) > TITLE_LIMIT:
        return _invalid("TITLE_TOO_LONG")
    if len(message) > MESSAGE_LIMIT:
        return _invalid("MESSAGE_TOO_LONG")
    if UNSAFE_VALUE.search(title) or UNSAFE_VALUE.search(message):
        return _invalid("UNSAFE_MESSAGE_CONTENT")
    return PushoverNotification(
        ADAPTER_VERSION, READY, priority, priority == 2, delivery_class,
        title, message, values["approval_required"], ("SAFE_NOTIFICATION_READY",),
    )


def adapt_notification(event: Any, *, adapter_version: Any = ADAPTER_VERSION) -> PushoverNotification:
    """Return an exact allowlisted safe contract without delivering it."""

    try:
        return _adapt(event, adapter_version)
    except Exception:
        return _invalid("INTERNAL_ADAPTER_ERROR")


__all__ = [
    "ADAPTER_VERSION", "INVALID_INPUT", "MESSAGE_LIMIT", "OUTPUT_FIELDS",
    "PushoverNotification", "READY", "TITLE_LIMIT", "adapt_notification",
]
