"""Inert-by-default one-item live verification adapter candidate.

The transport and idempotency claim are injected capabilities. This module
loads no secret, owns no HTTP client, persists nothing, and emits no raw value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable, Mapping

from product_verification import ErrorClass, VerificationObservation, evaluate_product_verification
from revenue_mvp_lifecycle_receipt import LIFECYCLE_RECEIPT_VERSION, LifecycleReceipt
from revenue_mvp_official_lifecycle_policy import (
    MAX_ERROR_RETRY_ATTEMPTS,
    MAX_ERROR_WAIT_SECONDS,
    InventorySignal,
)


ADAPTER_VERSION = "0.1-candidate"
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


class BoundedTransportFailure(Exception):
    """Caller-classified transport failure without raw exception text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("BOUNDED_TRANSPORT_FAILURE")


class _PrivateTarget:
    __slots__ = ("public_id", "content_id")

    def __init__(self, public_id: str, content_id: str) -> None:
        self.public_id = public_id
        self.content_id = content_id


@dataclass(frozen=True)
class BoundedVerificationResult:
    version: str
    status: str
    receipt: LifecycleReceipt | None
    request_attempts: int
    rate_limit_stopped: bool
    retry_performed: bool
    idempotency_claimed: bool
    api_calls: int
    database_writes: int
    production_writes: int
    reason_codes: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt")
        value["reason_codes"] = list(self.reason_codes)
        value["receipt_available"] = self.receipt is not None
        return value


def _result(
    status: str,
    *,
    receipt: LifecycleReceipt | None = None,
    attempts: int = 0,
    rate_limited: bool = False,
    retried: bool = False,
    claimed: bool = False,
    reasons: tuple[str, ...],
) -> BoundedVerificationResult:
    return BoundedVerificationResult(
        ADAPTER_VERSION, status, receipt, attempts, rate_limited, retried,
        claimed, attempts, 0, 0, tuple(sorted(set(reasons))),
    )


def _failure_payload(code: str, observed_at: datetime, status: int | str | None) -> dict[str, Any]:
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


def _sanitize_response(
    *, expected_content_id: str, http_status: Any, payload: Any,
    observed_at: datetime,
) -> dict[str, Any]:
    if type(http_status) is not int:
        return _failure_payload("UNKNOWN", observed_at, None)
    if http_status == 429:
        return _failure_payload("RATE_LIMIT", observed_at, 429)
    if not 200 <= http_status < 300:
        return _failure_payload(
            "TRANSIENT" if 500 <= http_status < 600 else "PERMANENT",
            observed_at, http_status,
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
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError
            returned_id = item.get("content_id")
            if not isinstance(returned_id, str) or CONTENT_ID_RE.fullmatch(returned_id) is None:
                raise ValueError
            affiliate_value = item.get("affiliateURL")
            sanitized_items.append({
                "content_id": returned_id,
                "affiliate_link_present": (
                    True if isinstance(affiliate_value, str) and bool(affiliate_value)
                    else False if affiliate_value is None else None
                ),
            })
        return {
            "expected_content_id": expected_content_id,
            "observed_at": observed_at,
            "call_status": "success",
            "error_class": None,
            "source_status_code": http_status,
            "result_count": count,
            "items": sanitized_items,
        }
    except Exception:
        return {
            "expected_content_id": expected_content_id,
            "observed_at": observed_at,
            "call_status": "success",
            "error_class": None,
            "source_status_code": http_status,
            "result_count": 0,
            "items": [{"content_id": "invalid/value", "affiliate_link_present": None}],
        }


def _receipt(public_id: str, observation: VerificationObservation) -> LifecycleReceipt:
    return LifecycleReceipt(
        LIFECYCLE_RECEIPT_VERSION,
        public_id,
        observation,
        InventorySignal.UNKNOWN,
        True,
    )


def run_bounded_verification(
    *,
    public_id: Any,
    content_id: Any,
    idempotency_key: Any,
    mode: str = DRY_RUN,
    explicit_live_approval: bool = False,
    secrets_confirmed: bool = False,
    item_limit: int = MAX_ITEMS,
    concurrency: int = MAX_CONCURRENCY,
    retry_limit: int = MAX_ERROR_RETRY_ATTEMPTS,
    retry_wait_seconds: int = MIN_RETRY_WAIT_SECONDS,
    transport: Callable[[str], tuple[int, Mapping[str, Any]]] | None = None,
    claim_once: Callable[[str], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[int], None] | None = None,
) -> BoundedVerificationResult:
    """Verify one private target; LIVE requires separate explicit capabilities."""

    try:
        if (
            not isinstance(public_id, str) or PUBLIC_ID_RE.fullmatch(public_id) is None
            or not isinstance(content_id, str) or CONTENT_ID_RE.fullmatch(content_id) is None
            or not isinstance(idempotency_key, str)
            or IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key) is None
            or item_limit != MAX_ITEMS
            or concurrency != MAX_CONCURRENCY
            or type(retry_limit) is not int
            or not 0 <= retry_limit <= MAX_ERROR_RETRY_ATTEMPTS
            or type(retry_wait_seconds) is not int
            or not MIN_RETRY_WAIT_SECONDS <= retry_wait_seconds <= MAX_ERROR_WAIT_SECONDS
            or mode not in {DRY_RUN, LIVE}
        ):
            return _result(FAIL_CLOSED, reasons=("VERIFICATION_INPUT_INVALID",))
        target = _PrivateTarget(public_id, content_id)
        if mode == DRY_RUN:
            return _result(
                DRY_RUN_READY,
                reasons=("LIVE_EXECUTION_REQUIRES_SEPARATE_APPROVAL",),
            )
        if explicit_live_approval is not True:
            return _result(BLOCKED, reasons=("LIVE_APPROVAL_REQUIRED",))
        if secrets_confirmed is not True:
            return _result(BLOCKED, reasons=("SECRET_EXISTENCE_CONFIRMATION_REQUIRED",))
        if not callable(transport) or not callable(claim_once) or not callable(clock) or not callable(sleeper):
            return _result(FAIL_CLOSED, reasons=("LIVE_CAPABILITY_INVALID",))
        try:
            claimed = claim_once(idempotency_key)
        except Exception:
            return _result(FAIL_CLOSED, reasons=("IDEMPOTENCY_CLAIM_FAILED",))
        if claimed is not True:
            return _result(BLOCKED, reasons=("IDEMPOTENCY_KEY_ALREADY_CLAIMED",))

        attempts = 0
        retried = False
        for attempt in range(retry_limit + 1):
            attempts += 1
            try:
                observed_at = clock()
                if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
                    raise ValueError
                http_status, payload = transport(target.content_id)
                sanitized = _sanitize_response(
                    expected_content_id=target.content_id,
                    http_status=http_status,
                    payload=payload,
                    observed_at=observed_at.astimezone(timezone.utc),
                )
            except BoundedTransportFailure as error:
                observed_at = clock()
                if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
                    return _result(FAIL_CLOSED, attempts=attempts, claimed=True,
                                   reasons=("OBSERVATION_CLOCK_INVALID",))
                code = error.code if error.code in {"RATE_LIMIT", "TRANSIENT", "PERMANENT"} else "UNKNOWN"
                sanitized = _failure_payload(code, observed_at.astimezone(timezone.utc), None)
            except Exception:
                return _result(FAIL_CLOSED, attempts=attempts, claimed=True,
                               reasons=("LIVE_ADAPTER_INTERNAL_ERROR",))

            observation = evaluate_product_verification(
                sanitized, as_of=observed_at.astimezone(timezone.utc)
            )
            if observation.observation.value == "API_RATE_LIMITED":
                return _result(
                    BLOCKED, receipt=_receipt(target.public_id, observation),
                    attempts=attempts, rate_limited=True, retried=retried,
                    claimed=True, reasons=("RATE_LIMIT_STOPPED",),
                )
            transient = observation.reason_codes == ("SOURCE_TRANSIENT_ERROR",)
            if transient and attempt < retry_limit:
                try:
                    sleeper(retry_wait_seconds)
                except Exception:
                    return _result(FAIL_CLOSED, attempts=attempts, claimed=True,
                                   reasons=("BOUNDED_RETRY_WAIT_FAILED",))
                retried = True
                continue
            return _result(
                VERIFIED, receipt=_receipt(target.public_id, observation),
                attempts=attempts, retried=retried, claimed=True,
                reasons=("SANITIZED_RECEIPT_CREATED",),
            )
        return _result(FAIL_CLOSED, attempts=attempts, claimed=True,
                       reasons=("RETRY_BOUND_EXHAUSTED",))
    except Exception:
        return _result(FAIL_CLOSED, reasons=("VERIFICATION_INTERNAL_ERROR",))


__all__ = [
    "ADAPTER_VERSION", "BLOCKED", "BoundedTransportFailure",
    "BoundedVerificationResult", "DRY_RUN", "DRY_RUN_READY", "FAIL_CLOSED",
    "LIVE", "MAX_CONCURRENCY", "MAX_ITEMS", "MIN_RETRY_WAIT_SECONDS",
    "VERIFIED", "run_bounded_verification",
]
