"""Memory-only v0.2 state-store planning candidate.

This module validates and serializes an explicit temporal series state, but it
does not create directories, read files, or write state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any

import temporal_probe_series_state as series_state


STORE_CANDIDATE_VERSION = "0.2-candidate"
WRITE_PLAN_READY = "WRITE_PLAN_READY"
WRITE_PLAN_BLOCKED = "WRITE_PLAN_BLOCKED"
MAX_STATE_BYTES = 1024 * 1024
STATE_FILENAME = re.compile(
    r"(?:rank|review)-offset[0-9]{6}-hits[0-9]{3,6}-"
    r"series-[a-f0-9]{16}-[0-9]{8}T[0-9]{12}Z\.json\Z"
)


@dataclass(frozen=True)
class SeriesStateWritePlan:
    version: str
    status: str
    success: bool
    filename: str | None
    document_sha256: str | None
    document_bytes: int | None
    series_aware_identity: bool
    filesystem_access_performed: bool
    state_write_authorized: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(code: str) -> SeriesStateWritePlan:
    return SeriesStateWritePlan(
        STORE_CANDIDATE_VERSION, WRITE_PLAN_BLOCKED, False,
        None, None, None, False, False, False, (code,),
    )


def _series_token(series_id: str) -> str:
    return hashlib.sha256(series_id.encode("utf-8")).hexdigest()[:16]


def _safe_filename(state: series_state.TemporalProbeSeriesState) -> str:
    legacy = state.legacy_state
    captured = legacy.captured_at.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    filename = (
        f"{legacy.source_sort}-offset{legacy.offset:06d}-"
        f"hits{legacy.hits:03d}-series-{_series_token(state.series_id)}-"
        f"{captured}.json"
    )
    if STATE_FILENAME.fullmatch(filename) is None:
        raise ValueError("unsafe series state filename")
    return filename


def plan_series_state_write(
    state: Any, *, as_of: datetime
) -> SeriesStateWritePlan:
    """Return bounded write metadata without returning or persisting content."""

    try:
        validation = series_state.validate_temporal_probe_series_state(
            state, as_of=as_of
        )
        if not validation.valid:
            return _blocked("INVALID_SERIES_STATE")
        serialized = series_state.serialize_temporal_probe_series_state(state)
        content = (serialized + "\n").encode("utf-8")
        if len(content) > MAX_STATE_BYTES:
            return _blocked("SERIES_STATE_TOO_LARGE")
        return SeriesStateWritePlan(
            STORE_CANDIDATE_VERSION,
            WRITE_PLAN_READY,
            True,
            _safe_filename(state),
            hashlib.sha256(content).hexdigest(),
            len(content),
            True,
            False,
            False,
            ("MEMORY_ONLY_WRITE_PLAN",),
        )
    except Exception:
        return _blocked("SERIES_STATE_WRITE_PLAN_ERROR")


__all__ = [
    "MAX_STATE_BYTES", "STATE_FILENAME", "STORE_CANDIDATE_VERSION",
    "SeriesStateWritePlan", "WRITE_PLAN_BLOCKED", "WRITE_PLAN_READY",
    "plan_series_state_write",
]
