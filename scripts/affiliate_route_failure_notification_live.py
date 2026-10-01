"""Explicit LIVE bridge for one deduplicated affiliate failure notification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sys
from typing import Any, Callable

import affiliate_route_failure_notification_candidate as candidate
import unattended_runtime as runtime


VERSION = "0.1"
MAX_INPUT_BYTES = 65536


@dataclass(frozen=True)
class LiveResult:
    version: str
    status: str
    runtime_status: str | None
    notification_selected: bool
    duplicate_suppressed: bool
    delivery_attempted: bool
    delivery_succeeded: bool
    external_send_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def run(wrapper_result: Any, *, incident_day_utc: str,
        credential_loader: Callable[..., Any] | None = None,
        transport: Callable[..., Any] | None = None,
        ledger: Any = None) -> LiveResult:
    occurred_at = f"{incident_day_utc}T00:00:00Z"
    summary, _notification = candidate.prepare(
        wrapper_result, occurred_at=occurred_at
    )
    if summary.status == "SUPPRESSED_HEALTHY":
        return LiveResult(
            VERSION, "SUPPRESSED_HEALTHY", None, False, False, False,
            False, False, ("NO_FAILURE_NOTIFICATION",),
        )
    if not summary.notification_ready:
        return LiveResult(
            VERSION, "FAILED_SAFE", None, False, False, False, False,
            False, ("NOTIFICATION_CANDIDATE_NOT_READY",),
        )
    event = candidate.failure_event(occurred_at)
    if event is None:
        return LiveResult(
            VERSION, "FAILED_SAFE", None, False, False, False, False,
            False, ("SAFE_NOTIFICATION_EVENT_REJECTED",),
        )
    delivered = runtime.process_notification(
        event,
        mode="LIVE_NOTIFICATION",
        live_notification_confirmed=True,
        credential_loader=credential_loader,
        transport=transport,
        ledger=ledger,
    )
    duplicate = delivered.runtime_status == "NOTIFICATION_DUPLICATE_SUPPRESSED"
    success = (
        delivered.runtime_status == "NOTIFICATION_DELIVERED"
        and delivered.delivery_attempted is True
        and delivered.delivery_succeeded is True
    )
    accepted = success or duplicate
    return LiveResult(
        VERSION,
        "DELIVERED" if success else
        "DUPLICATE_SUPPRESSED" if duplicate else "FAILED_SAFE",
        delivered.runtime_status,
        delivered.notification_selected,
        duplicate,
        delivered.delivery_attempted,
        delivered.delivery_succeeded,
        delivered.delivery_attempted,
        ("FAILURE_NOTIFICATION_DELIVERED",) if success else
        ("FAILURE_NOTIFICATION_DUPLICATE_SUPPRESSED",) if duplicate else
        tuple(delivered.reason_codes) or ("FAILURE_NOTIFICATION_FAILED",),
    )


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input too large")
        payload = json.loads(raw.decode("utf-8"))
        incident_day = datetime.now(timezone.utc).date().isoformat()
        result = run(payload, incident_day_utc=incident_day)
    except Exception:
        result = LiveResult(
            VERSION, "FAILED_SAFE", None, False, False, False, False,
            False, ("LIVE_NOTIFICATION_INPUT_INVALID",),
        )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {
        "SUPPRESSED_HEALTHY", "DELIVERED", "DUPLICATE_SUPPRESSED"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
