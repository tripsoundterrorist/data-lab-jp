"""Validate a manual, aggregate-only Cloudflare Free dashboard observation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any

import revenue_mvp_cloudflare_free_capacity_static_review as limits


VERSION = "0.1"
VERIFIED = "CLOUDFLARE_FREE_CAPACITY_VERIFIED"
BLOCKED = "CLOUDFLARE_DASHBOARD_OBSERVATION_BLOCKED"
FIELDS = frozenset({
    "version",
    "observed_at",
    "workers_requests_24h",
    "workers_cpu_limit_errors_24h",
    "d1_rows_read_24h",
    "d1_rows_written_24h",
    "d1_database_storage_bytes",
    "d1_account_storage_bytes",
    "active_cron_triggers",
})
COUNT_FIELDS = FIELDS - {"version", "observed_at", "active_cron_triggers"}


@dataclass(frozen=True)
class DashboardObservation:
    version: str
    status: str
    observed_at: str | None
    cloudflare_free_plan_capacity_verified: bool
    unexpected_cron_absent: bool
    paid_plan_change_allowed: bool
    production_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(*reasons: str, observed_at: str | None = None) -> DashboardObservation:
    return DashboardObservation(
        VERSION, BLOCKED, observed_at, False, False, False, False,
        tuple(sorted(reasons)),
    )


def validate(payload: Any, *, now: datetime | None = None) -> DashboardObservation:
    if type(payload) is not dict or set(payload) != FIELDS:
        return _blocked("ROOT_SCHEMA_INVALID")
    if payload["version"] != VERSION:
        return _blocked("VERSION_INVALID")
    observed_at = payload["observed_at"]
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError
        observed = observed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return _blocked("OBSERVED_AT_INVALID")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_seconds = (current - observed).total_seconds()
    if age_seconds < 0 or age_seconds > 24 * 60 * 60:
        return _blocked("OBSERVATION_NOT_CURRENT", observed_at=observed_at)
    for field in COUNT_FIELDS:
        if type(payload[field]) is not int or payload[field] < 0:
            return _blocked("COUNT_INVALID", observed_at=observed_at)
    triggers = payload["active_cron_triggers"]
    if type(triggers) is not list or any(
        not isinstance(value, str) or not value.strip() for value in triggers
    ) or len(set(triggers)) != len(triggers):
        return _blocked("CRON_TRIGGER_SET_INVALID", observed_at=observed_at)

    reasons: set[str] = set()
    if payload["workers_requests_24h"] >= limits.WORKERS_FREE_REQUESTS_PER_DAY:
        reasons.add("WORKERS_REQUEST_LIMIT_REACHED")
    if payload["workers_cpu_limit_errors_24h"]:
        reasons.add("WORKERS_CPU_LIMIT_ERRORS_PRESENT")
    if payload["d1_rows_read_24h"] >= limits.D1_FREE_ROWS_READ_PER_DAY:
        reasons.add("D1_READ_LIMIT_REACHED")
    if payload["d1_rows_written_24h"] >= limits.D1_FREE_ROWS_WRITTEN_PER_DAY:
        reasons.add("D1_WRITE_LIMIT_REACHED")
    if payload["d1_database_storage_bytes"] >= limits.D1_FREE_DATABASE_BYTES:
        reasons.add("D1_DATABASE_STORAGE_LIMIT_REACHED")
    if payload["d1_account_storage_bytes"] >= limits.D1_FREE_ACCOUNT_STORAGE_BYTES:
        reasons.add("D1_ACCOUNT_STORAGE_LIMIT_REACHED")
    if triggers:
        reasons.add("UNEXPECTED_ACTIVE_CRON_PRESENT")

    verified = not reasons
    return DashboardObservation(
        VERSION,
        VERIFIED if verified else BLOCKED,
        observed_at,
        verified,
        not triggers,
        False,
        False,
        tuple(sorted(reasons)),
    )


def main() -> int:
    import sys
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = _blocked("JSON_INVALID")
    else:
        result = validate(payload)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == VERIFIED else 2


if __name__ == "__main__":
    raise SystemExit(main())
