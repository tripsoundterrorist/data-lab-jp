"""Non-live Factory-to-Runtime handoff; no event metadata or queue analysis."""

from dataclasses import asdict, dataclass

import unattended_job_queue as queue
import unattended_runtime as runtime


BLOCKED_DISPATCH_VERSION = "0.1"
_SUCCESS = frozenset({"NOTIFICATION_READY", "NOTIFICATION_DELIVERED",
                      "NOTIFICATION_DUPLICATE_SUPPRESSED"})
_FAILURE = frozenset({"INVALID_INPUT", "NOTIFICATION_FAILED_SAFE"})


@dataclass(frozen=True)
class BlockedDispatchResult:
    dispatch_version: str
    dispatch_status: str
    event_generated: bool
    runtime_handoff: bool
    runtime_mode: str | None
    runtime_status: str | None
    reason_code: str

    def to_dict(self):
        return asdict(self)


def dispatch_queue_blocked(decision, identity, *, mode="DRY_RUN", ledger=None,
                           credential_loader=None, transport=None):
    """Pass an unchanged Factory object to Runtime at most once.

    Optional dependencies are test fixtures, operated on only by Runtime.
    No CLI or LIVE activation is provided in this version.
    """
    generated, handed_off = False, False
    safe_mode = mode if type(mode) is str and mode in {"DRY_RUN", "MOCK_RUNTIME"} else None

    def output(status, reason, runtime_status=None):
        return BlockedDispatchResult(BLOCKED_DISPATCH_VERSION, status, generated,
                                     handed_off, safe_mode, runtime_status, reason)

    if safe_mode is None:
        return output("BLOCKED", "DISPATCH_MODE_BLOCKED")
    if mode == "MOCK_RUNTIME" and (not callable(credential_loader) or not callable(transport)):
        return output("BLOCKED", "MOCK_DEPENDENCIES_REQUIRED")
    try:
        event = queue.build_queue_blocked_safe_event(decision, identity)
    except Exception:
        return output("BLOCKED", "FACTORY_FAILED_CLOSED")
    if type(event) is not queue.QueueNotificationEventV02:
        return output("BLOCKED", "FACTORY_FAILED_CLOSED")
    generated = True
    try:
        handed_off = True
        result = runtime.process_notification(event, mode=mode, ledger=ledger,
                                              credential_loader=credential_loader, transport=transport)
        if (type(result) is not runtime.RuntimeResult or set(vars(result)) != runtime.OUTPUT_FIELDS
                or result.runtime_version != runtime.RUNTIME_VERSION or result.runtime_mode != mode
                or type(result.runtime_status) is not str or result.runtime_status not in _SUCCESS | _FAILURE
                or result.event_type not in (None, event.event_type)
                or any(type(getattr(result, k)) is not bool for k in (
                    "notification_selected", "notification_suppressed", "delivery_attempted",
                    "delivery_succeeded", "approval_required", "emergency_blocked"))
                or (mode == "DRY_RUN" and (result.delivery_attempted or result.delivery_succeeded))
                or (result.runtime_status == "NOTIFICATION_DELIVERED" and (
                    not result.delivery_attempted or not result.delivery_succeeded or result.emergency_blocked))
                or (result.runtime_status == "NOTIFICATION_DUPLICATE_SUPPRESSED" and (
                    result.delivery_attempted or result.delivery_succeeded))):
            return output("FAILED_SAFE", "RUNTIME_RESULT_INVALID")
        if result.runtime_status in _FAILURE:
            return output("FAILED_SAFE", "RUNTIME_NOTIFICATION_FAILED", result.runtime_status)
        return output("COMPLETED", "RUNTIME_HANDOFF_COMPLETED", result.runtime_status)
    except Exception:
        return output("FAILED_SAFE", "RUNTIME_HANDOFF_FAILED")
