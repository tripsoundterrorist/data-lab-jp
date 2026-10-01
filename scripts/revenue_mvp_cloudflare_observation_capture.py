"""Build a sanitized Cloudflare observation only from complete manual input."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import revenue_mvp_cloudflare_dashboard_observation as observation


VERSION = "0.1"
RAW_FIELDS = frozenset({
    "workers_requests_24h",
    "workers_cpu_limit_errors_24h",
    "d1_rows_read_24h",
    "d1_rows_written_24h",
    "d1_database_storage_bytes",
    "d1_account_storage_bytes",
    "active_cron_triggers",
})


def build_evidence(
    raw: Any,
    *,
    observed_at: datetime,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, observation.DashboardObservation]:
    if (
        type(raw) is not dict
        or set(raw) != RAW_FIELDS
        or type(observed_at) is not datetime
        or observed_at.tzinfo is None
    ):
        result = observation.validate(None, now=now)
        return None, result
    payload = {
        "version": VERSION,
        "observed_at": observed_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        **raw,
    }
    result = observation.validate(payload, now=now)
    return (payload if result.status == observation.VERIFIED else None), result


def main() -> int:
    import sys
    try:
        raw = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raw = None
    evidence, result = build_evidence(
        raw,
        observed_at=datetime.now(timezone.utc),
    )
    output: Any = evidence if evidence is not None else result.to_dict()
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if evidence is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
