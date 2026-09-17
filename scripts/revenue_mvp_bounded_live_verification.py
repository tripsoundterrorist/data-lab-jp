"""Inert-by-default one-item live verification adapter candidate.

All external capabilities are injected. This module owns no HTTP client,
secret loader, persistence, logger, publication action, or production action.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from product_verification import (
    ErrorClass,
    Observation,
    VerificationObservation,
    evaluate_product_verification,
)
from revenue_mvp_lifecycle_receipt import (
    LIFECYCLE_RECEIPT_VERSION,
    LifecycleReceipt,
    public_item_id,
)
from revenue_mvp_official_lifecycle_policy import (
    MAX_ERROR_RETRY_ATTEMPTS,
    MAX_ERROR_WAIT_SECONDS,
    InventorySignal,
)


ADAPTER_VERSION = "0.2-candidate"
DRY_RUN = "DRY_RUN"
LIVE = "LIVE"
DRY_RUN_READY = "DRY_RUN_READY"
VERIFIED = "VERIFIED"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
PUBLIC_ID_RE = re.compile(r"itm_[0-9a-f]{24}\Z")
CONTENT_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}\Z")
MIN_RETRY_WAIT_SECONDS = 1
MAX_ITEMS = 1
MAX_CONCURRENCY = 1
MAX_FRESHNESS_AGE_SECONDS = 300
ALLOWED_CONTEXT = ("FANZA", "digital", "videoa")
ALLOWED_AFFILIATE_HOST_SUFFIXES = (
    "dmm.co.jp",
    "dmm.com",
    "fanza.com",
    "fanza.co.jp",
)


class BoundedTransportFailure(Exception):
    """Caller-classified failure without raw exception text or values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("BOUNDED_TRANSPORT_FAILURE")


class _PrivateTarget:
    __slots__ = ("public_id", "content_id")

    def __init__(self, public_id: str, content_id: str) -> None:
        object.__setattr__(self, "public_id", public_id)
        object.__setattr__(self, "content_id", content_id)

    def __setattr__(self, _name: str, _value: Any) -> None:
        raise AttributeError("PRIVATE_TARGET_IMMUTABLE")


class _ExecutionState:
    __slots__ = (
        "request_attempts",
        "api_calls",
        "rate_limit_stopped",
        "retry_performed",
        "idempotency_claimed",
        "global_slot_claimed",
    )

    def __init__(self) -> None:
        self.request_attempts = 0
        self.api_calls = 0
        self.rate_limit_stopped = False
        self.retry_performed = False
        self.idempotency_claimed = False
        self.global_slot_claimed = False


@dataclass(frozen=True)
class BoundedVerificationResult:
    version: str
    status: str
    receipt: LifecycleReceipt | None
    request_attempts: int
    rate_limit_stopped: bool
    retry_performed: bool
    idempotency_claimed: bool
    global_slot_claimed: bool
    api_calls: int
    database_writes: int
    production_writes: int
    eligibility_granted: bool
    reason_codes: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt")
        value["reason_codes"] = list(self.reason_codes)
        value["receipt_available"] = self.receipt is not None
        return value


def _result(
    status: str,
    state: _ExecutionState,
    *,
    receipt: LifecycleReceipt | None = None,
    reasons: tuple[str, ...],
) -> BoundedVerificationResult:
    return BoundedVerificationResult(
        ADAPTER_VERSION,
        status,
        receipt,
        state.request_attempts,
        state.rate_limit_stopped,
        state.retry_performed,
        state.idempotency_claimed,
        state.global_slot_claimed,
        state.api_calls,
        0,
        0,
        False,
        tuple(sorted(set(reasons))),
    )


def _failure_payload(
    code: str, observed_at: datetime, status: int | str | None
) -> dict[str, Any]:
    error_class = {
        "RATE_LIMIT": ErrorClass.RATE_LIMITED.value,
        "TRANSIENT": ErrorClass.TRANSIENT_ERROR.value,
        "PERMANENT": ErrorClass.PERMANENT_ERROR.value,
    }.get(code, ErrorClass.UNKNOWN_ERROR.value)
    return {
        "expected_content_id": "internal-placeholder",
        "observed_at": observed_at,
        "call_status": "failure",
        "error_class": error_class,
        "source_status_code": status,
        "result_count": None,
        "items": [],
    }


def _affiliate_presence(value: Any) -> tuple[bool | None, str]:
    if value is None:
        return False, "AFFILIATE_URL_ABSENT"
    if not isinstance(value, str) or not value or value != value.strip():
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    if len(value) > 2048 or any(
        ord(character) < 33 or ord(character) == 127 for character in value
    ):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    if re.search(r"%(?:00|0a|0d)", value, re.IGNORECASE):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.port not in (None, 443):
            return None, "AFFILIATE_URL_VALIDATION_FAILED"
    except (TypeError, ValueError):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    host_allowed = bool(hostname) and any(
        hostname == suffix or hostname.endswith("." + suffix)
        for suffix in ALLOWED_AFFILIATE_HOST_SUFFIXES
    )
    if (
        parsed.scheme.casefold() != "https"
        or not host_allowed
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    return True, "AFFILIATE_URL_VALIDATED"


def _sanitize_response(
    *,
    expected_content_id: str,
    http_status: Any,
    payload: Any,
    observed_at: datetime,
) -> tuple[dict[str, Any], str | None]:
    if type(http_status) is not int:
        return _failure_payload("UNKNOWN", observed_at, None), None
    if http_status == 429:
        return _failure_payload("RATE_LIMIT", observed_at, 429), None
    if not 200 <= http_status < 300:
        return (
            _failure_payload(
                "TRANSIENT" if 500 <= http_status < 600 else "PERMANENT",
                observed_at,
                http_status,
            ),
            None,
        )
    try:
        result = payload.get("result") if isinstance(payload, Mapping) else None
        if not isinstance(result, Mapping) or str(result.get("status")) != "200":
            raise ValueError
        items = result.get("items")
        count = result.get("result_count")
        if isinstance(count, str) and count.isascii() and count.isdigit():
            count = int(count)
        if type(count) is not int or count < 0 or not isinstance(items, list):
            raise ValueError
        sanitized_items: list[dict[str, Any]] = []
        validation_reason: str | None = None
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError
            returned_id = item.get("content_id")
            if (
                not isinstance(returned_id, str)
                or CONTENT_ID_RE.fullmatch(returned_id) is None
            ):
                raise ValueError
            presence, reason = _affiliate_presence(item.get("affiliateURL"))
            if len(items) == 1:
                validation_reason = reason
            sanitized_items.append(
                {
                    "content_id": returned_id,
                    "affiliate_link_present": presence,
                }
            )
        return (
            {
                "expected_content_id": expected_content_id,
                "observed_at": observed_at,
                "call_status": "success",
                "error_class": None,
                "source_status_code": http_status,
                "result_count": count,
                "items": sanitized_items,
            },
            validation_reason,
        )
    except Exception:
        return (
            {
                "expected_content_id": expected_content_id,
                "observed_at": observed_at,
                "call_status": "success",
                "error_class": None,
                "source_status_code": http_status,
                "result_count": 0,
                "items": [
                    {
                        "content_id": "invalid/value",
                        "affiliate_link_present": None,
                    }
                ],
            },
            "AFFILIATE_URL_VALIDATION_UNCONFIRMED",
        )


def _read_clock(clock: Callable[[], datetime]) -> datetime | None:
    try:
        value = clock()
    except Exception:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def _receipt(
    public_id: str,
    observation: VerificationObservation,
    *,
    freshness_confirmed: bool,
    evaluated_at: datetime,
    max_age_seconds: int,
) -> LifecycleReceipt:
    return LifecycleReceipt(
        LIFECYCLE_RECEIPT_VERSION,
        public_id,
        observation,
        InventorySignal.UNKNOWN,
        freshness_confirmed,
        evaluated_at,
        max_age_seconds,
    )


def run_bounded_verification(
    *,
    public_id: Any,
    site: Any,
    service: Any,
    floor: Any,
    content_id: Any,
    idempotency_key: Any,
    mode: str = DRY_RUN,
    explicit_live_approval: bool = False,
    secrets_confirmed: bool = False,
    item_limit: int = MAX_ITEMS,
    concurrency: int = MAX_CONCURRENCY,
    retry_limit: int = MAX_ERROR_RETRY_ATTEMPTS,
    retry_wait_seconds: int = MIN_RETRY_WAIT_SECONDS,
    freshness_max_age_seconds: int = MAX_FRESHNESS_AGE_SECONDS,
    transport: Callable[[str], tuple[int, Mapping[str, Any]]] | None = None,
    claim_once: Callable[[str], bool] | None = None,
    claim_global_slot: Callable[[str], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[int], None] | None = None,
) -> BoundedVerificationResult:
    """Create a sanitized receipt, never eligibility or publication authority."""

    state = _ExecutionState()
    try:
        context = (site, service, floor)
        if (
            not isinstance(public_id, str)
            or PUBLIC_ID_RE.fullmatch(public_id) is None
            or context != ALLOWED_CONTEXT
            or not isinstance(content_id, str)
            or CONTENT_ID_RE.fullmatch(content_id) is None
            or public_item_id(site, service, floor, content_id) != public_id
            or not isinstance(idempotency_key, str)
            or IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key) is None
            or item_limit != MAX_ITEMS
            or concurrency != MAX_CONCURRENCY
            or type(retry_limit) is not int
            or not 0 <= retry_limit <= MAX_ERROR_RETRY_ATTEMPTS
            or type(retry_wait_seconds) is not int
            or not MIN_RETRY_WAIT_SECONDS
            <= retry_wait_seconds
            <= MAX_ERROR_WAIT_SECONDS
            or type(freshness_max_age_seconds) is not int
            or not 1
            <= freshness_max_age_seconds
            <= MAX_FRESHNESS_AGE_SECONDS
            or mode not in {DRY_RUN, LIVE}
        ):
            return _result(
                FAIL_CLOSED, state, reasons=("TARGET_BINDING_OR_INPUT_INVALID",)
            )
        target = _PrivateTarget(public_id, content_id)
        if mode == DRY_RUN:
            return _result(
                DRY_RUN_READY,
                state,
                reasons=("LIVE_EXECUTION_REQUIRES_SEPARATE_APPROVAL",),
            )
        if explicit_live_approval is not True:
            return _result(BLOCKED, state, reasons=("LIVE_APPROVAL_REQUIRED",))
        if secrets_confirmed is not True:
            return _result(
                BLOCKED,
                state,
                reasons=("SECRET_EXISTENCE_CONFIRMATION_REQUIRED",),
            )
        if not all(
            callable(capability)
            for capability in (
                transport,
                claim_once,
                claim_global_slot,
                clock,
                sleeper,
            )
        ):
            return _result(
                FAIL_CLOSED, state, reasons=("LIVE_CAPABILITY_INVALID",)
            )
        try:
            state.idempotency_claimed = claim_once(idempotency_key) is True
        except Exception:
            return _result(
                FAIL_CLOSED, state, reasons=("IDEMPOTENCY_CLAIM_FAILED",)
            )
        if not state.idempotency_claimed:
            return _result(
                BLOCKED, state, reasons=("IDEMPOTENCY_KEY_ALREADY_CLAIMED",)
            )
        try:
            state.global_slot_claimed = claim_global_slot(idempotency_key) is True
        except Exception:
            return _result(
                FAIL_CLOSED, state, reasons=("GLOBAL_CONCURRENCY_CLAIM_FAILED",)
            )
        if not state.global_slot_claimed:
            return _result(
                BLOCKED,
                state,
                reasons=("GLOBAL_CONCURRENCY_SLOT_UNAVAILABLE",),
            )

        last_evaluated_at: datetime | None = None
        for attempt in range(retry_limit + 1):
            request_started_at = _read_clock(clock)
            if request_started_at is None:
                return _result(
                    FAIL_CLOSED, state, reasons=("PRE_REQUEST_CLOCK_INVALID",)
                )
            if (
                last_evaluated_at is not None
                and request_started_at < last_evaluated_at
            ):
                return _result(
                    FAIL_CLOSED,
                    state,
                    reasons=("RETRY_CLOCK_REVERSED",),
                )
            if attempt > 0:
                state.retry_performed = True
            state.request_attempts += 1
            state.api_calls += 1
            transport_failure: BoundedTransportFailure | None = None
            unexpected_transport_failure = False
            try:
                http_status, payload = transport(target.content_id)
            except BoundedTransportFailure as error:
                transport_failure = error
                http_status, payload = None, None
            except Exception:
                unexpected_transport_failure = True
                http_status, payload = None, None
            if http_status == 429 or (
                transport_failure is not None
                and transport_failure.code == "RATE_LIMIT"
            ):
                state.rate_limit_stopped = True
            observed_at = _read_clock(clock)
            if observed_at is None:
                return _result(
                    FAIL_CLOSED, state, reasons=("POST_REQUEST_CLOCK_INVALID",)
                )
            if observed_at < request_started_at:
                return _result(
                    FAIL_CLOSED, state, reasons=("OBSERVATION_CLOCK_REVERSED",)
                )
            if unexpected_transport_failure:
                return _result(
                    FAIL_CLOSED, state, reasons=("LIVE_TRANSPORT_FAILED",)
                )
            if transport_failure is not None:
                code = (
                    transport_failure.code
                    if transport_failure.code
                    in {"RATE_LIMIT", "TRANSIENT", "PERMANENT"}
                    else "UNKNOWN"
                )
                sanitized = _failure_payload(code, observed_at, None)
                url_reason = None
            else:
                sanitized, url_reason = _sanitize_response(
                    expected_content_id=target.content_id,
                    http_status=http_status,
                    payload=payload,
                    observed_at=observed_at,
                )
            evaluated_at = _read_clock(clock)
            if evaluated_at is None:
                return _result(
                    FAIL_CLOSED, state, reasons=("EVALUATION_CLOCK_INVALID",)
                )
            if evaluated_at < observed_at:
                return _result(
                    FAIL_CLOSED, state, reasons=("EVALUATION_CLOCK_REVERSED",)
                )
            last_evaluated_at = evaluated_at
            observation = evaluate_product_verification(
                sanitized, as_of=evaluated_at
            )
            if (
                url_reason is not None
                and observation.observation is Observation.API_ITEM_VISIBLE
            ):
                observation = replace(
                    observation,
                    reason_codes=tuple(
                        sorted(set(observation.reason_codes + (url_reason,)))
                    ),
                )
            fresh = (
                evaluated_at - observed_at
            ).total_seconds() <= freshness_max_age_seconds
            receipt = _receipt(
                target.public_id,
                observation,
                freshness_confirmed=fresh,
                evaluated_at=evaluated_at,
                max_age_seconds=freshness_max_age_seconds,
            )
            if observation.observation is Observation.API_RATE_LIMITED:
                return _result(
                    BLOCKED,
                    state,
                    receipt=receipt,
                    reasons=("RATE_LIMIT_STOPPED",),
                )
            transient = observation.reason_codes == ("SOURCE_TRANSIENT_ERROR",)
            if transient and attempt < retry_limit:
                try:
                    sleeper(retry_wait_seconds)
                except Exception:
                    return _result(
                        FAIL_CLOSED,
                        state,
                        reasons=("BOUNDED_RETRY_WAIT_FAILED",),
                    )
                continue
            reasons = ["SANITIZED_RECEIPT_CREATED_NOT_ELIGIBILITY"]
            if not fresh:
                reasons.append("RECEIPT_FRESHNESS_NOT_CONFIRMED")
            return _result(
                VERIFIED, state, receipt=receipt, reasons=tuple(reasons)
            )
        return _result(
            FAIL_CLOSED, state, reasons=("RETRY_BOUND_EXHAUSTED",)
        )
    except Exception:
        return _result(
            FAIL_CLOSED, state, reasons=("VERIFICATION_INTERNAL_ERROR",)
        )


__all__ = [
    "ADAPTER_VERSION",
    "BLOCKED",
    "BoundedTransportFailure",
    "BoundedVerificationResult",
    "DRY_RUN",
    "DRY_RUN_READY",
    "FAIL_CLOSED",
    "LIVE",
    "MAX_CONCURRENCY",
    "MAX_FRESHNESS_AGE_SECONDS",
    "MAX_ITEMS",
    "MIN_RETRY_WAIT_SECONDS",
    "VERIFIED",
    "run_bounded_verification",
]
