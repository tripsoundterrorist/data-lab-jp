"""Inert runner/preflight for the bounded verification adapter.

This module has no HTTP, secret, storage, logging, or deployment capability.
All effects are injected and remain disabled in the default DRY_RUN mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable, Mapping

import revenue_mvp_bounded_live_verification as adapter
from revenue_mvp_lifecycle_receipt import LifecycleReceipt


RUNNER_VERSION = "0.1-candidate"
APPROVAL_VERSION = "0.1"
APPROVAL_SCOPE = "REVENUE_MVP_BOUNDED_LIVE_VERIFICATION"
MAX_APPROVAL_WINDOW_SECONDS = 900
REQUIRED_SECRET_NAMES = ("DMM_API_ID", "DMM_AFFILIATE_ID")
OPAQUE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}\Z")


@dataclass(frozen=True)
class LiveApproval:
    version: str
    scope: str
    approval_id: str
    idempotency_key: str
    issued_at: datetime
    expires_at: datetime
    one_shot: bool
    live_execution_allowed: bool


@dataclass(frozen=True)
class RunnerResult:
    version: str
    status: str
    receipt: LifecycleReceipt | None
    approval_valid: bool
    secret_names_confirmed: bool
    idempotency_claimed: bool
    global_slot_claimed: bool
    global_slot_release_attempted: bool
    global_slot_released: bool
    api_calls: int
    adapter_database_writes: int
    runner_writes: int
    production_writes: int
    eligibility_granted: bool
    reason_codes: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "receipt_available": self.receipt is not None,
            "approval_valid": self.approval_valid,
            "secret_names_confirmed": self.secret_names_confirmed,
            "idempotency_claimed": self.idempotency_claimed,
            "global_slot_claimed": self.global_slot_claimed,
            "global_slot_release_attempted": self.global_slot_release_attempted,
            "global_slot_released": self.global_slot_released,
            "api_calls": self.api_calls,
            "adapter_database_writes": self.adapter_database_writes,
            "runner_writes": self.runner_writes,
            "production_writes": self.production_writes,
            "eligibility_granted": self.eligibility_granted,
            "reason_codes": list(self.reason_codes),
        }


def validate_live_approval(
    approval: Any,
    *,
    evaluated_at: Any,
    expected_idempotency_key: Any,
) -> tuple[bool, tuple[str, ...]]:
    """Pure validation of scope, expiry and one-shot authorization."""

    reasons: list[str] = []
    if type(approval) is not LiveApproval:
        return False, ("LIVE_APPROVAL_REQUIRED",)
    if approval.version != APPROVAL_VERSION:
        reasons.append("APPROVAL_VERSION_INVALID")
    if approval.scope != APPROVAL_SCOPE:
        reasons.append("APPROVAL_SCOPE_INVALID")
    if (
        not isinstance(approval.approval_id, str)
        or OPAQUE_ID_RE.fullmatch(approval.approval_id) is None
    ):
        reasons.append("APPROVAL_ID_INVALID")
    if (
        not isinstance(expected_idempotency_key, str)
        or OPAQUE_ID_RE.fullmatch(expected_idempotency_key) is None
        or approval.idempotency_key != expected_idempotency_key
    ):
        reasons.append("APPROVAL_IDEMPOTENCY_BINDING_INVALID")
    if approval.one_shot is not True:
        reasons.append("APPROVAL_ONE_SHOT_REQUIRED")
    if approval.live_execution_allowed is not True:
        reasons.append("LIVE_EXECUTION_NOT_APPROVED")
    timestamps = (approval.issued_at, approval.expires_at, evaluated_at)
    if any(
        not isinstance(value, datetime) or value.tzinfo is None
        for value in timestamps
    ):
        reasons.append("APPROVAL_TIME_INVALID")
    else:
        try:
            issued = approval.issued_at.astimezone(timezone.utc)
            expires = approval.expires_at.astimezone(timezone.utc)
            evaluated = evaluated_at.astimezone(timezone.utc)
            if not issued <= evaluated < expires:
                reasons.append("APPROVAL_NOT_CURRENT")
            if not (
                0
                < (expires - issued).total_seconds()
                <= MAX_APPROVAL_WINDOW_SECONDS
            ):
                reasons.append("APPROVAL_WINDOW_INVALID")
        except Exception:
            reasons.append("APPROVAL_TIME_INVALID")
    return not reasons, tuple(sorted(set(reasons)))


def _result(
    status: str,
    *,
    receipt: LifecycleReceipt | None = None,
    approval_valid: bool = False,
    secrets_confirmed: bool = False,
    adapter_result: adapter.BoundedVerificationResult | None = None,
    release_attempted: bool = False,
    released: bool = False,
    global_claimed: bool = False,
    reasons: tuple[str, ...],
) -> RunnerResult:
    return RunnerResult(
        RUNNER_VERSION,
        status,
        receipt,
        approval_valid,
        secrets_confirmed,
        adapter_result.idempotency_claimed if adapter_result else False,
        global_claimed or (
            adapter_result.global_slot_claimed if adapter_result else False
        ),
        release_attempted,
        released,
        adapter_result.api_calls if adapter_result else 0,
        adapter_result.database_writes if adapter_result else 0,
        0,
        adapter_result.production_writes if adapter_result else 0,
        False,
        tuple(sorted(set(reasons))),
    )


def _secret_names_confirmed(
    checker: Callable[[tuple[str, ...]], Mapping[str, bool]],
) -> bool:
    try:
        result = checker(REQUIRED_SECRET_NAMES)
    except Exception:
        return False
    return (
        isinstance(result, Mapping)
        and set(result) == set(REQUIRED_SECRET_NAMES)
        and all(type(result[name]) is bool and result[name] for name in REQUIRED_SECRET_NAMES)
    )


def _read_runner_clock(clock: Callable[[], datetime]) -> datetime | None:
    try:
        value = clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc)
    except Exception:
        return None


def run_verification(
    *,
    public_id: Any,
    site: Any,
    service: Any,
    floor: Any,
    content_id: Any,
    idempotency_key: Any,
    mode: str = adapter.DRY_RUN,
    approval: LiveApproval | None = None,
    approval_evaluated_at: datetime | None = None,
    secret_name_checker: Callable[[tuple[str, ...]], Mapping[str, bool]] | None = None,
    claim_idempotency_once: Callable[[str], bool] | None = None,
    claim_global_slot: Callable[[str], bool] | None = None,
    release_global_slot: Callable[[str], bool] | None = None,
    transport: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[int], None] | None = None,
) -> RunnerResult:
    """Run only through the public adapter contract; default mode is inert."""

    _ = approval_evaluated_at  # Compatibility input; never LIVE time authority.
    adapter_result: adapter.BoundedVerificationResult | None = None
    global_claimed = False
    release_attempted = False
    released = False
    last_approval_checked_at: datetime | None = None

    def tracked_global_claim(key: str) -> bool:
        nonlocal global_claimed
        claimed = claim_global_slot(key)
        global_claimed = claimed is True
        return global_claimed

    def pre_transport_approval_guard(request_started_at: datetime) -> bool:
        nonlocal last_approval_checked_at
        current = _read_runner_clock(clock)
        if current is None or last_approval_checked_at is None:
            return False
        if (
            request_started_at < last_approval_checked_at
            or current < request_started_at
            or current < last_approval_checked_at
        ):
            return False
        valid, _ = validate_live_approval(
            approval,
            evaluated_at=current,
            expected_idempotency_key=idempotency_key,
        )
        if not valid:
            return False
        last_approval_checked_at = current
        return True

    if mode == adapter.DRY_RUN:
        try:
            adapter_result = adapter.run_bounded_verification(
                public_id=public_id,
                site=site,
                service=service,
                floor=floor,
                content_id=content_id,
                idempotency_key=idempotency_key,
                mode=adapter.DRY_RUN,
            )
        except Exception:
            return _result(
                adapter.FAIL_CLOSED,
                reasons=("DRY_RUN_ADAPTER_FAILED",),
            )
        return _result(
            adapter_result.status,
            adapter_result=adapter_result,
            reasons=tuple(adapter_result.reason_codes),
        )
    if mode != adapter.LIVE:
        return _result(
            adapter.FAIL_CLOSED,
            reasons=("RUNNER_MODE_INVALID",),
        )

    if type(approval) is not LiveApproval:
        return _result(adapter.BLOCKED, reasons=("LIVE_APPROVAL_REQUIRED",))
    if not callable(clock):
        return _result(
            adapter.FAIL_CLOSED,
            reasons=("APPROVAL_CLOCK_INVALID",),
        )
    initial_approval_time = _read_runner_clock(clock)
    if initial_approval_time is None:
        return _result(
            adapter.FAIL_CLOSED,
            reasons=("APPROVAL_CLOCK_INVALID",),
        )
    valid_approval, approval_reasons = validate_live_approval(
        approval,
        evaluated_at=initial_approval_time,
        expected_idempotency_key=idempotency_key,
    )
    if not valid_approval:
        return _result(adapter.BLOCKED, reasons=approval_reasons)
    if not callable(secret_name_checker):
        return _result(
            adapter.FAIL_CLOSED,
            approval_valid=True,
            reasons=("SECRET_NAME_CHECKER_INVALID",),
        )
    secrets_confirmed = _secret_names_confirmed(secret_name_checker)
    if not secrets_confirmed:
        return _result(
            adapter.BLOCKED,
            approval_valid=True,
            reasons=("REQUIRED_SECRET_NAMES_NOT_CONFIRMED",),
        )
    post_secret_time = _read_runner_clock(clock)
    if post_secret_time is None:
        return _result(
            adapter.FAIL_CLOSED,
            approval_valid=True,
            secrets_confirmed=True,
            reasons=("APPROVAL_CLOCK_INVALID",),
        )
    if post_secret_time < initial_approval_time:
        return _result(
            adapter.FAIL_CLOSED,
            approval_valid=True,
            secrets_confirmed=True,
            reasons=("APPROVAL_CLOCK_REVERSED",),
        )
    valid_approval, approval_reasons = validate_live_approval(
        approval,
        evaluated_at=post_secret_time,
        expected_idempotency_key=idempotency_key,
    )
    if not valid_approval:
        return _result(
            adapter.BLOCKED,
            approval_valid=False,
            secrets_confirmed=True,
            reasons=approval_reasons,
        )
    last_approval_checked_at = post_secret_time
    if not all(
        callable(capability)
        for capability in (
            claim_idempotency_once,
            claim_global_slot,
            release_global_slot,
            transport,
            sleeper,
        )
    ):
        return _result(
            adapter.FAIL_CLOSED,
            approval_valid=True,
            secrets_confirmed=True,
            reasons=("RUNNER_CAPABILITY_INVALID",),
        )

    adapter_failed = False
    try:
        adapter_result = adapter.run_bounded_verification(
            public_id=public_id,
            site=site,
            service=service,
            floor=floor,
            content_id=content_id,
            idempotency_key=idempotency_key,
            mode=adapter.LIVE,
            explicit_live_approval=True,
            secrets_confirmed=True,
            transport=transport,
            claim_once=claim_idempotency_once,
            claim_global_slot=tracked_global_claim,
            pre_transport_guard=pre_transport_approval_guard,
            clock=clock,
            sleeper=sleeper,
        )
    except Exception:
        adapter_failed = True
    finally:
        if global_claimed:
            release_attempted = True
            try:
                released = release_global_slot(idempotency_key) is True
            except Exception:
                released = False

    if global_claimed and not released:
        return _result(
            adapter.FAIL_CLOSED,
            approval_valid=True,
            secrets_confirmed=True,
            adapter_result=adapter_result,
            release_attempted=release_attempted,
            released=False,
            global_claimed=True,
            reasons=("GLOBAL_SLOT_RELEASE_FAILED",),
        )
    if adapter_failed or adapter_result is None:
        return _result(
            adapter.FAIL_CLOSED,
            approval_valid=True,
            secrets_confirmed=True,
            release_attempted=release_attempted,
            released=released,
            global_claimed=global_claimed,
            reasons=("ADAPTER_EXECUTION_FAILED",),
        )
    return _result(
        adapter_result.status,
        receipt=adapter_result.receipt,
        approval_valid=True,
        secrets_confirmed=True,
        adapter_result=adapter_result,
        release_attempted=release_attempted,
        released=released,
        global_claimed=global_claimed,
        reasons=tuple(adapter_result.reason_codes),
    )


__all__ = [
    "APPROVAL_SCOPE",
    "APPROVAL_VERSION",
    "LiveApproval",
    "MAX_APPROVAL_WINDOW_SECONDS",
    "REQUIRED_SECRET_NAMES",
    "RUNNER_VERSION",
    "RunnerResult",
    "run_verification",
    "validate_live_approval",
]
