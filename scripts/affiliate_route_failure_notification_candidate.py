"""Pure notification candidate for affiliate revalidation/route failures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pushover_notification_adapter as adapter
import unattended_job_queue as queue


VERSION = "0.1"


@dataclass(frozen=True)
class CandidateResult:
    version: str
    status: str
    failure_detected: bool
    event_created: bool
    notification_ready: bool
    delivery_class: str | None
    pushover_priority: int | None
    external_send_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, *, failure: bool = False, event: bool = False,
            ready: bool = False, delivery: str | None = None,
            priority: int | None = None, reason: str) -> CandidateResult:
    return CandidateResult(
        VERSION, status, failure, event, ready, delivery, priority, False,
        (reason,),
    )


def failure_event(occurred_at: Any):
    """Build the one fixed safe event used by DRY_RUN and LIVE bridges."""
    return queue.create_event(
        event_version=queue.EVENT_VERSION,
        event_type="JOB_FAILED_SAFE",
        job_id="affiliate-route-health",
        job_type="affiliate_revalidation",
        severity="ERROR",
        state=queue.FAILED_SAFE,
        approval_required=False,
        summary_code="AFFILIATE_ROUTE_HEALTH_FAILED",
        occurred_at=occurred_at,
    )


def prepare(wrapper_result: Any, *, occurred_at: Any) -> tuple[CandidateResult, adapter.PushoverNotification | None]:
    """Return a safe summary plus an in-memory fixed notification contract."""

    try:
        if not isinstance(wrapper_result, Mapping) or set(wrapper_result) != {
            "version", "revalidation", "public_route_health",
        }:
            return _result("FAILED_SAFE", reason="WRAPPER_RESULT_INVALID"), None
        revalidation = wrapper_result["revalidation"]
        health = wrapper_result["public_route_health"]
        if not isinstance(revalidation, Mapping) or not isinstance(health, Mapping):
            return _result("FAILED_SAFE", reason="WRAPPER_RESULT_INVALID"), None
        if wrapper_result["version"] != "0.2":
            return _result("FAILED_SAFE", reason="WRAPPER_VERSION_UNSUPPORTED"), None
        healthy = (
            revalidation.get("status") == "COMPLETED"
            and revalidation.get("mode") == "LIVE"
            and health.get("status") == "HEALTHY"
            and health.get("external_write_performed") is False
        )
        if healthy:
            return _result("SUPPRESSED_HEALTHY", reason="NO_FAILURE_NOTIFICATION"), None
        event = failure_event(occurred_at)
        if event is None:
            return _result(
                "FAILED_SAFE", failure=True,
                reason="SAFE_NOTIFICATION_EVENT_REJECTED",
            ), None
        notification = adapter.adapt_notification(event)
        if notification.notification_status != adapter.READY:
            return _result(
                "FAILED_SAFE", failure=True, event=True,
                reason="NOTIFICATION_ADAPTER_REJECTED",
            ), None
        return _result(
            "READY_FOR_EXPLICIT_LIVE_SEND", failure=True, event=True,
            ready=True, delivery=notification.delivery_class,
            priority=notification.pushover_priority,
            reason="SAFE_FAILURE_NOTIFICATION_READY",
        ), notification
    except Exception:
        return _result("FAILED_SAFE", reason="CANDIDATE_BUILD_FAILED"), None


def build(wrapper_result: Any, *, occurred_at: Any) -> CandidateResult:
    """Map only exact aggregate wrapper state; never send a notification."""

    return prepare(wrapper_result, occurred_at=occurred_at)[0]


__all__ = ["CandidateResult", "VERSION", "build", "failure_event", "prepare"]
