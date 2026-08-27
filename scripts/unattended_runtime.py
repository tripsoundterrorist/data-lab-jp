"""Safe orchestration boundary for queue events, notification adapter and sender."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping, MutableSet

import pushover_notification_adapter as notification_adapter
import pushover_sender
import unattended_job_queue as queue
from notification_ledger import LedgerError, ledger_for_mode
from ledger_recovery import HEALTHY, RECOVERABLE_NO_WRITE, inspect_ledger


RUNTIME_VERSION = "0.1"
MODES = frozenset({"DRY_RUN", "MOCK_RUNTIME", "LIVE_NOTIFICATION"})
AUTO_NOTIFY_EVENTS = frozenset({
    "JOB_WAITING_APPROVAL", "JOB_FAILED_SAFE", "QUEUE_BLOCKED", "JOB_COMPLETED",
    "CRITICAL_STOP",
})
SUPPRESSED_EVENTS = frozenset({
    "JOB_STARTED", "JOB_CHECKPOINTED", "JOB_SWITCHED", "QUEUE_IDLE",
})
EVENT_FIELDS = frozenset({
    "event_version", "event_type", "job_id", "job_type", "severity", "state",
    "approval_required", "summary_code", "occurred_at",
})
OUTPUT_FIELDS = frozenset({
    "runtime_version", "runtime_mode", "runtime_status", "event_type",
    "notification_selected", "notification_suppressed", "delivery_attempted",
    "delivery_succeeded", "approval_required", "emergency_blocked", "reason_codes",
})
EXPECTED_STATES = {
    "JOB_STARTED": "RUNNING", "JOB_COMPLETED": "DONE",
    "JOB_FAILED_SAFE": "FAILED_SAFE", "JOB_WAITING_APPROVAL": "WAITING_APPROVAL",
    "JOB_CHECKPOINTED": "CHECKPOINTED", "JOB_SWITCHED": "READY",
    "QUEUE_IDLE": "READY", "QUEUE_BLOCKED": "BLOCKED", "CRITICAL_STOP": "FAILED_SAFE",
}


@dataclass(frozen=True)
class RuntimeResult:
    runtime_version: str
    runtime_mode: str
    runtime_status: str
    event_type: str | None
    notification_selected: bool
    notification_suppressed: bool
    delivery_attempted: bool
    delivery_succeeded: bool
    approval_required: bool
    emergency_blocked: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _result(mode: Any, status: str, *, event_type: str | None = None,
            selected: bool = False, suppressed: bool = False,
            attempted: bool = False, succeeded: bool = False,
            approval: bool = False, emergency: bool = False,
            reasons: tuple[str, ...]) -> RuntimeResult:
    return RuntimeResult(
        RUNTIME_VERSION, mode if type(mode) is str and mode in MODES else "DRY_RUN", status, event_type,
        selected, suppressed, attempted, succeeded, approval, emergency,
        tuple(sorted(set(reasons))),
    )


def _event_mapping(event: Any) -> Mapping[str, Any] | None:
    if isinstance(event, queue.NotificationEvent):
        return event.to_dict()
    return event if isinstance(event, Mapping) else None


def event_identity(event: Any) -> str | None:
    """Return a deterministic opaque identity for an already-safe exact event."""

    value = _event_mapping(event)
    if value is None or set(value) != EVENT_FIELDS:
        return None
    try:
        canonical = json.dumps(
            {key: value[key] for key in sorted(EVENT_FIELDS)},
            ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_event(event: Any) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    value = _event_mapping(event)
    if value is None:
        return None, ("EVENT_CONTRACT_INVALID",)
    if set(value) != EVENT_FIELDS:
        return None, ("EVENT_SCHEMA_INVALID",)
    validated = queue.create_event(**dict(value))
    if validated is None:
        return None, ("QUEUE_EVENT_INVALID",)
    event_type = value["event_type"]
    if value["approval_required"] != (event_type == "JOB_WAITING_APPROVAL"):
        return None, ("APPROVAL_FLAG_CONTRADICTORY",)
    if value["state"] != EXPECTED_STATES[event_type]:
        return None, ("EVENT_STATE_CONTRADICTORY",)
    return value, ()


def _runtime(
    event: Any, *, runtime_version: Any, mode: Any,
    live_notification_confirmed: Any, seen_event_ids: MutableSet[str] | None,
    adapter_fn: Callable[..., Any], sender_fn: Callable[..., Any],
    credential_loader: Callable[..., Any] | None, transport: Callable[..., Any] | None,
    ledger: Any,
) -> RuntimeResult:
    if runtime_version != RUNTIME_VERSION:
        return _result(mode, "INVALID_INPUT", reasons=("RUNTIME_VERSION_UNSUPPORTED",))
    if mode not in MODES:
        return _result(mode, "INVALID_INPUT", reasons=("RUNTIME_MODE_INVALID",))
    if not isinstance(live_notification_confirmed, bool):
        return _result(mode, "INVALID_INPUT", reasons=("LIVE_CONFIRMATION_INVALID",))
    value, reasons = _validate_event(event)
    if value is None:
        return _result(mode, "INVALID_INPUT", reasons=reasons)
    event_type = value["event_type"]
    approval = value["approval_required"]
    identity = event_identity(value)
    if identity is None:
        return _result(mode, "INVALID_INPUT", event_type=event_type,
                       approval=approval, reasons=("EVENT_IDENTITY_INVALID",))
    if seen_event_ids is not None:
        if not isinstance(seen_event_ids, MutableSet):
            return _result(mode, "INVALID_INPUT", event_type=event_type,
                           approval=approval, reasons=("DEDUPLICATION_STORE_INVALID",))
        if identity in seen_event_ids:
            return _result(mode, "DUPLICATE_EVENT_SUPPRESSED", event_type=event_type,
                           suppressed=True, approval=approval,
                           reasons=("DUPLICATE_EVENT_SUPPRESSED",))
    if event_type in SUPPRESSED_EVENTS:
        if seen_event_ids is not None:
            seen_event_ids.add(identity)
        return _result(mode, "NOTIFICATION_SUPPRESSED", event_type=event_type,
                       suppressed=True, approval=approval,
                       reasons=("EVENT_NOT_AUTO_NOTIFIED",))
    if event_type not in AUTO_NOTIFY_EVENTS:
        return _result(mode, "INVALID_INPUT", event_type=event_type,
                       approval=approval, reasons=("EVENT_POLICY_UNKNOWN",))
    if mode == "LIVE_NOTIFICATION" and not live_notification_confirmed:
        return _result(mode, "LIVE_NOTIFICATION_NOT_CONFIRMED", event_type=event_type,
                       selected=True, approval=approval,
                       reasons=("EXPLICIT_LIVE_CONFIRMATION_REQUIRED",))
    delivery = None
    try:
        with ledger_for_mode(mode, ledger) as store:
            # Explicit test stores must never load real credentials or send live.
            if mode == "LIVE_NOTIFICATION" and store.test_only and (transport is None or credential_loader is None):
                raise LedgerError("LEDGER_TEST_TRANSPORT_REQUIRED")
            recovery = inspect_ledger(store)
            if (recovery.recovery_status not in {HEALTHY, RECOVERABLE_NO_WRITE}
                    or (mode == "LIVE_NOTIFICATION" and recovery.recovery_status != HEALTHY)):
                return _result(mode, "NOTIFICATION_FAILED_SAFE", event_type=event_type,
                               selected=True, approval=approval,
                               reasons=recovery.reason_codes)
            with store.transaction(writable=(mode != "DRY_RUN")) as transaction:
                if transaction.lookup(identity) == "DELIVERED":
                    return _result(mode, "NOTIFICATION_DUPLICATE_SUPPRESSED", event_type=event_type,
                                   selected=True, suppressed=True, approval=approval,
                                   reasons=("PERSISTENT_DUPLICATE_SUPPRESSED",))
                delivery = _deliver(value, mode=mode, live_notification_confirmed=live_notification_confirmed,
                                    adapter_fn=adapter_fn, sender_fn=sender_fn,
                                    credential_loader=credential_loader, transport=transport,
                                    seen_event_ids=seen_event_ids, identity=identity)
                if (mode != "DRY_RUN" and delivery.runtime_status == "NOTIFICATION_DELIVERED"
                        and delivery.delivery_succeeded is True):
                    transaction.record_success(identity, event_type)
                return delivery
    except LedgerError as error:
        return _result(mode, "NOTIFICATION_FAILED_SAFE", event_type=event_type,
                       selected=True, approval=approval,
                       attempted=delivery.delivery_attempted if delivery else False,
                       succeeded=delivery.delivery_succeeded if delivery else False,
                       emergency=delivery.emergency_blocked if delivery else False,
                       reasons=(error.code,))


def _deliver(value, *, mode, live_notification_confirmed, adapter_fn, sender_fn,
             credential_loader, transport, seen_event_ids, identity):
    event_type, approval = value["event_type"], value["approval_required"]
    adapted = adapter_fn(value)
    adapted_dict = adapted.to_dict() if isinstance(adapted, notification_adapter.PushoverNotification) else adapted
    if (not isinstance(adapted_dict, Mapping)
            or set(adapted_dict) != notification_adapter.OUTPUT_FIELDS
            or adapted_dict.get("notification_status") != notification_adapter.READY):
        return _result(mode, "NOTIFICATION_FAILED_SAFE", event_type=event_type,
                       selected=True, approval=approval,
                       reasons=("ADAPTER_RESULT_INVALID",))
    sender_mode = {"DRY_RUN": "DRY_RUN", "MOCK_RUNTIME": "MOCK_SEND", "LIVE_NOTIFICATION": "LIVE_SEND"}[mode]
    sent = sender_fn(
        adapted, mode=sender_mode,
        live_send_confirmed=(mode == "LIVE_NOTIFICATION" and live_notification_confirmed),
        credential_loader=credential_loader, transport=transport,
    )
    sent_dict = sent.to_dict() if isinstance(sent, pushover_sender.SenderResult) else sent
    if not isinstance(sent_dict, Mapping) or set(sent_dict) != pushover_sender.OUTPUT_FIELDS:
        return _result(mode, "NOTIFICATION_FAILED_SAFE", event_type=event_type,
                       selected=True, approval=approval,
                       reasons=("SENDER_RESULT_INVALID",))
    if (sent_dict["sender_version"] != pushover_sender.SENDER_VERSION
            or sent_dict["sender_mode"] != sender_mode
            or any(type(sent_dict[key]) is not bool for key in (
                "delivery_attempted", "delivery_succeeded", "suppressible_skipped",
                "emergency_blocked", "credential_presence_ok"))
            or (sent_dict["delivery_succeeded"] and (
                sent_dict["sender_status"] != "SEND_SUCCEEDED"
                or not sent_dict["delivery_attempted"] or sent_dict["emergency_blocked"]
                or mode == "DRY_RUN" or event_type == "CRITICAL_STOP"))):
        return _result(mode, "NOTIFICATION_FAILED_SAFE", event_type=event_type,
                       selected=True, approval=approval, reasons=("SENDER_RESULT_INVALID",))
    if seen_event_ids is not None:
        seen_event_ids.add(identity)
    attempted = sent_dict.get("delivery_attempted") is True
    succeeded = sent_dict.get("delivery_succeeded") is True
    emergency = sent_dict.get("emergency_blocked") is True
    if emergency:
        status, final_reasons = "EMERGENCY_SEND_BLOCKED", ("EMERGENCY_SEND_BLOCKED",)
    elif succeeded:
        status, final_reasons = "NOTIFICATION_DELIVERED", ("NOTIFICATION_DELIVERED",)
    elif sent_dict.get("sender_status") == "DRY_RUN_READY":
        status, final_reasons = "NOTIFICATION_READY", ("DRY_RUN_VALIDATED",)
    else:
        status, final_reasons = "NOTIFICATION_FAILED_SAFE", ("SENDER_DELIVERY_FAILED",)
    return _result(mode, status, event_type=event_type, selected=True,
                   attempted=attempted, succeeded=succeeded, approval=approval,
                   emergency=emergency, reasons=final_reasons)


def process_notification(
    event: Any, *, runtime_version: Any = RUNTIME_VERSION, mode: Any = "DRY_RUN",
    live_notification_confirmed: Any = False,
    seen_event_ids: MutableSet[str] | None = None,
    adapter_fn: Callable[..., Any] = notification_adapter.adapt_notification,
    sender_fn: Callable[..., Any] = pushover_sender.send_notification,
    credential_loader: Callable[..., Any] | None = None,
    transport: Callable[..., Any] | None = None,
    ledger: Any = None,
) -> RuntimeResult:
    try:
        return _runtime(
            event, runtime_version=runtime_version, mode=mode,
            live_notification_confirmed=live_notification_confirmed,
            seen_event_ids=seen_event_ids, adapter_fn=adapter_fn, sender_fn=sender_fn,
            credential_loader=credential_loader, transport=transport,
            ledger=ledger,
        )
    except Exception:
        return _result(mode, "NOTIFICATION_FAILED_SAFE", reasons=("INTERNAL_RUNTIME_ERROR",))


__all__ = [
    "AUTO_NOTIFY_EVENTS", "EVENT_FIELDS", "MODES", "OUTPUT_FIELDS",
    "RUNTIME_VERSION", "RuntimeResult", "SUPPRESSED_EVENTS", "event_identity",
    "process_notification",
]
