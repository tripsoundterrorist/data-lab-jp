"""Pure document discovery candidate for v0.2 temporal series states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import temporal_probe_series_state as series_state


DISCOVERY_VERSION = "0.1"
LATEST_FOUND = "LATEST_FOUND"
EXPLICIT_BASELINE_CANDIDATE = "EXPLICIT_BASELINE_CANDIDATE"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class SeriesDiscoveryResult:
    version: str
    status: str
    success: bool
    comparison_candidate: bool
    baseline_candidate: bool
    selected: series_state.TemporalProbeSeriesState | None
    same_series_previous_count: int
    legacy_excluded_count: int
    cross_series_excluded_count: int
    reason_codes: tuple[str, ...]

    def safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "success": self.success,
            "comparison_candidate": self.comparison_candidate,
            "baseline_candidate": self.baseline_candidate,
            "same_series_previous_count": self.same_series_previous_count,
            "legacy_excluded_count": self.legacy_excluded_count,
            "cross_series_excluded_count": self.cross_series_excluded_count,
            "reason_codes": list(self.reason_codes),
        }


def _failure(reason: str) -> SeriesDiscoveryResult:
    return SeriesDiscoveryResult(
        DISCOVERY_VERSION, FAIL_CLOSED, False, False, False, None,
        0, 0, 0, (reason,),
    )


def discover_latest_same_series(
    current: Any,
    documents: Iterable[Any],
    *,
    as_of: datetime,
) -> SeriesDiscoveryResult:
    """Select only an unambiguous earlier state from the explicit series."""

    try:
        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or as_of.utcoffset() is None
            or not series_state.validate_temporal_probe_series_state(
                current, as_of=as_of
            ).valid
            or isinstance(documents, (str, bytes))
        ):
            return _failure("INVALID_DISCOVERY_INPUT")
        values = tuple(documents)
        same_series: list[series_state.TemporalProbeSeriesState] = []
        legacy_count = 0
        cross_series_count = 0
        base_identity = current.legacy_state.population_identity
        for document in values:
            parsed = series_state.deserialize_temporal_probe_series_state(
                document
            )
            if parsed is None:
                classification = series_state.classify_temporal_state_document(
                    document
                )
                if classification.status == series_state.LEGACY_READ_ONLY:
                    legacy_count += 1
                    continue
                return _failure("UNREADABLE_DISCOVERY_DOCUMENT")
            if not series_state.validate_temporal_probe_series_state(
                parsed, as_of=as_of
            ).valid:
                return _failure("INVALID_SERIES_STATE_DOCUMENT")
            if parsed.legacy_state.population_identity != base_identity:
                continue
            if parsed.series_id != current.series_id:
                cross_series_count += 1
                continue
            if parsed.legacy_state.captured_at >= current.legacy_state.captured_at:
                return _failure("NON_PREVIOUS_SAME_SERIES_STATE")
            same_series.append(parsed)
        timestamps = [
            value.legacy_state.captured_at.astimezone(timezone.utc)
            for value in same_series
        ]
        if len(timestamps) != len(set(timestamps)):
            return _failure("AMBIGUOUS_SAME_SERIES_TIMESTAMP")
        if not same_series:
            return SeriesDiscoveryResult(
                DISCOVERY_VERSION,
                EXPLICIT_BASELINE_CANDIDATE,
                True,
                False,
                True,
                None,
                0,
                legacy_count,
                cross_series_count,
                ("NO_SAME_SERIES_PREVIOUS_STATE",),
            )
        selected = max(
            same_series, key=lambda value: value.legacy_state.captured_at
        )
        return SeriesDiscoveryResult(
            DISCOVERY_VERSION,
            LATEST_FOUND,
            True,
            True,
            False,
            selected,
            len(same_series),
            legacy_count,
            cross_series_count,
            ("SAME_SERIES_LATEST_SELECTED",),
        )
    except Exception:
        return _failure("SERIES_DISCOVERY_ERROR")


__all__ = [
    "DISCOVERY_VERSION", "EXPLICIT_BASELINE_CANDIDATE", "FAIL_CLOSED",
    "LATEST_FOUND", "SeriesDiscoveryResult", "discover_latest_same_series",
]
