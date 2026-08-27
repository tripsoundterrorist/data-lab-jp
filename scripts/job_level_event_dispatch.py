"""Non-live, job-level dispatch. Core validates transitions; Runtime owns delivery."""

from dataclasses import asdict, dataclass

import unattended_job_queue as queue
import unattended_runtime as runtime


DISPATCH_VERSION = "0.1"
_MAPPINGS = {
    "APPROVAL_WAITING_TRANSITION": ("JOB_WAITING_APPROVAL", "WARN", True, "APPROVAL_WAIT_TRANSITION"),
    "FAILED_SAFE_TRANSITION": ("JOB_FAILED_SAFE", "ERROR", False, "SAFE_FAILURE_TRANSITION"),
    "COMPLETION_TRANSITION": ("JOB_COMPLETED", "INFO", False, "COMPLETION_TRANSITION"),
}
_RUNTIME_STATUSES = frozenset({"NOTIFICATION_READY", "NOTIFICATION_DELIVERED",
    "NOTIFICATION_DUPLICATE_SUPPRESSED", "NOTIFICATION_FAILED_SAFE", "INVALID_INPUT"})


@dataclass(frozen=True)
class DispatchResult:
    dispatch_version: str
    dispatch_status: str
    validation_version: str | None
    transition_class: str | None
    event_generated: bool
    event_type: str | None
    runtime_handoff: bool
    runtime_mode: str | None
    runtime_status: str | None
    reason_code: str

    def to_dict(self):
        return asdict(self)


def dispatch_transition(source, *, mode="DRY_RUN", ledger=None,
                        credential_loader=None, transport=None):
    """Validate first, then hand off at most once. No CLI or LIVE confirmation.

    Optional dependencies are internal test fixtures passed only to Runtime.
    Runtime enforces isolated storage for MOCK_RUNTIME; no storage logic lives here.
    """
    validation_version, classification, event_type = None, None, None
    generated, handed_off = False, False
    safe_mode = mode if type(mode) is str and mode in {"DRY_RUN", "MOCK_RUNTIME"} else None

    def output(status, reason, runtime_status=None):
        return DispatchResult(DISPATCH_VERSION, status, validation_version, classification,
                              generated, event_type, handed_off, safe_mode, runtime_status, reason)

    try:
        checked = queue.validate_job_transition_result(source)
        if (type(checked) is not queue.TransitionValidationResult
                or set(vars(checked)) != {"validation_version", "valid", "transition_class", "reason_code"}
                or type(checked.validation_version) is not str
                or checked.validation_version != queue.TRANSITION_VALIDATION_VERSION
                or checked.valid is not True
                or type(checked.transition_class) is not str
                or checked.transition_class not in {*_MAPPINGS, "APPROVAL_READY_TRANSITION"}
                or checked.reason_code != "TRANSITION_CONTRACT_VALID"):
            return output("BLOCKED", "CORE_VALIDATION_REJECTED")
        validation_version, classification = checked.validation_version, checked.transition_class
        if safe_mode is None:
            return output("BLOCKED", "DISPATCH_MODE_BLOCKED")
        if classification == "APPROVAL_READY_TRANSITION":
            return output("SUPPRESSED", "TRANSITION_NOT_NOTIFICATION_ELIGIBLE")
        if mode == "MOCK_RUNTIME" and (not callable(credential_loader) or not callable(transport)):
            return output("BLOCKED", "MOCK_DEPENDENCIES_REQUIRED")
        mapped_type, severity, approval, summary = _MAPPINGS[classification]
        event = {
            "event_version": queue.EVENT_VERSION, "event_type": mapped_type,
            "job_id": source.job_id, "job_type": source.job_type,
            "state": source.new_state, "occurred_at": source.occurred_at,
            "severity": severity, "approval_required": approval, "summary_code": summary,
        }
        event_type, generated, handed_off = mapped_type, True, True
        result = runtime.process_notification(event, mode=mode, ledger=ledger,
                                              credential_loader=credential_loader, transport=transport)
        if (type(result) is not runtime.RuntimeResult
                or set(vars(result)) != runtime.OUTPUT_FIELDS
                or result.runtime_version != runtime.RUNTIME_VERSION or result.runtime_mode != mode
                or result.event_type not in {None, event_type}
                or type(result.runtime_status) is not str or result.runtime_status not in _RUNTIME_STATUSES
                or any(type(getattr(result, key)) is not bool for key in (
                    "notification_selected", "notification_suppressed", "delivery_attempted",
                    "delivery_succeeded", "approval_required", "emergency_blocked"))
                or (mode == "DRY_RUN" and (result.delivery_attempted or result.delivery_succeeded))
                or (result.runtime_status == "NOTIFICATION_DELIVERED" and (
                    not result.delivery_attempted or not result.delivery_succeeded or result.emergency_blocked))
                or (result.runtime_status == "NOTIFICATION_DUPLICATE_SUPPRESSED" and result.delivery_attempted)):
            return output("FAILED_SAFE", "RUNTIME_RESULT_INVALID")
        if result.runtime_status in {"NOTIFICATION_FAILED_SAFE", "INVALID_INPUT"}:
            return output("FAILED_SAFE", "RUNTIME_NOTIFICATION_FAILED", result.runtime_status)
        return output("COMPLETED", "RUNTIME_HANDOFF_COMPLETED", result.runtime_status)
    except Exception:
        return output("FAILED_SAFE", "DISPATCH_OPERATION_FAILED")
