"""Fail-closed detector for an unexpected recurring revalidation cadence.

The guard reads a private Cloudflare D1 SQL export and reports aggregates only.
It never emits identifiers, URLs, SQL, credentials, or exception text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Iterable


VERSION = "0.1"
PASS = "PASS"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = (
    ROOT / "runtime" / "private"
    / "affiliate-runtime-post-initial-batch-000-20261001.sql"
)
UPSTREAM_REASON = "PROVIDER_UPSTREAM_UNAVAILABLE"
EVENT_PATTERN = re.compile(
    r'^INSERT INTO "affiliate_lifecycle_revalidation_event" '
    r'\("id","public_id","checked_at","outcome",'
    r'"affiliate_enabled_after","reason_code"\) VALUES\('
    r"\d+,'[^']+','([^']+)','([^']+)',([01]),'([^']+)'\);$"
)


@dataclass(frozen=True)
class RevalidationEvent:
    checked_at: datetime
    outcome: str
    affiliate_enabled_after: int
    reason_code: str


@dataclass(frozen=True)
class CadenceGuardResult:
    version: str
    status: str
    event_count: int
    run_group_count: int
    upstream_unavailable_event_count: int
    upstream_unavailable_run_group_count: int
    hourly_sequence_count: int
    additional_live_batch_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def parse_export(lines: Iterable[str]) -> tuple[RevalidationEvent, ...]:
    events = []
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line.startswith('INSERT INTO "affiliate_lifecycle_revalidation_event"'):
            continue
        match = EVENT_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError("event row malformed")
        checked_at, outcome, enabled, reason = match.groups()
        if outcome not in {"VALID", "NOT_AVAILABLE", "UNCONFIRMED"}:
            raise ValueError("outcome invalid")
        events.append(
            RevalidationEvent(
                _parse_timestamp(checked_at), outcome, int(enabled), reason
            )
        )
    if not events:
        raise ValueError("event evidence missing")
    return tuple(events)


def assess(events: object) -> CadenceGuardResult:
    if not isinstance(events, tuple) or not events or any(
        not isinstance(event, RevalidationEvent) for event in events
    ):
        return CadenceGuardResult(
            VERSION, FAIL_CLOSED, 0, 0, 0, 0, 0, False,
            ("REVALIDATION_EVENT_EVIDENCE_INVALID",),
        )

    groups = sorted({event.checked_at for event in events})
    upstream_events = tuple(
        event for event in events
        if event.outcome == "UNCONFIRMED"
        and event.affiliate_enabled_after == 0
        and event.reason_code == UPSTREAM_REASON
    )
    upstream_groups = sorted({event.checked_at for event in upstream_events})

    hourly_sequences = 0
    current_length = 1
    for previous, current in zip(upstream_groups, upstream_groups[1:]):
        interval_seconds = (current - previous).total_seconds()
        if 45 * 60 <= interval_seconds <= 75 * 60:
            current_length += 1
        else:
            if current_length >= 3:
                hourly_sequences += 1
            current_length = 1
    if current_length >= 3:
        hourly_sequences += 1

    reasons = ()
    status = PASS
    if hourly_sequences:
        status = BLOCKED
        reasons = ("UNEXPECTED_RECURRING_UPSTREAM_FAILURE_CADENCE",)

    return CadenceGuardResult(
        VERSION,
        status,
        len(events),
        len(groups),
        len(upstream_events),
        len(upstream_groups),
        hourly_sequences,
        status == PASS,
        reasons,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) > 1:
        result = assess(None)
    else:
        path = Path(arguments[0]) if arguments else DEFAULT_EXPORT
        try:
            with path.open("r", encoding="utf-8", newline="") as source:
                result = assess(parse_export(source))
        except (OSError, UnicodeError, ValueError):
            result = assess(None)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
