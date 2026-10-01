"""DRY_RUN-only bridge from aggregate route health to Pushover sender."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sys
from typing import Any, Callable

import affiliate_route_failure_notification_candidate as candidate
import pushover_sender as sender


VERSION = "0.1"
MAX_INPUT_BYTES = 65536


@dataclass(frozen=True)
class DryRunResult:
    version: str
    status: str
    candidate_status: str
    sender_status: str | None
    credential_presence_ok: bool
    delivery_attempted: bool
    external_send_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def run(wrapper_result: Any, *, occurred_at: str,
        credential_loader: Callable[[], tuple[str | None, str | None]] | None = None) -> DryRunResult:
    summary, notification = candidate.prepare(wrapper_result, occurred_at=occurred_at)
    if summary.status == "SUPPRESSED_HEALTHY":
        return DryRunResult(
            VERSION, "SUPPRESSED_HEALTHY", summary.status, None, False,
            False, False, ("NO_FAILURE_NOTIFICATION",),
        )
    if not summary.notification_ready or notification is None:
        return DryRunResult(
            VERSION, "FAILED_SAFE", summary.status, None, False,
            False, False, ("NOTIFICATION_CANDIDATE_NOT_READY",),
        )
    sent = sender.send_notification(
        notification, mode="DRY_RUN", live_send_confirmed=False,
        credential_loader=credential_loader,
    )
    ready = (
        sent.sender_status == "DRY_RUN_READY"
        and sent.credential_presence_ok is True
        and sent.delivery_attempted is False
        and sent.delivery_succeeded is False
    )
    return DryRunResult(
        VERSION, "READY_NO_SEND" if ready else "FAILED_SAFE",
        summary.status, sent.sender_status, sent.credential_presence_ok,
        sent.delivery_attempted, False,
        ("DRY_RUN_NOTIFICATION_VALIDATED",) if ready else
        ("DRY_RUN_NOTIFICATION_REJECTED",),
    )


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input too large")
        payload = json.loads(raw.decode("utf-8"))
        occurred_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        result = run(payload, occurred_at=occurred_at)
    except Exception:
        result = DryRunResult(
            VERSION, "FAILED_SAFE", "INVALID_INPUT", None, False, False,
            False, ("DRY_RUN_INPUT_INVALID",),
        )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {"SUPPRESSED_HEALTHY", "READY_NO_SEND"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
