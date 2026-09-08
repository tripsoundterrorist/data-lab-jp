"""Pure v0.2 candidate state contract with explicit series boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Iterable, Mapping

import temporal_probe_state as legacy


STATE_SCHEMA_VERSION = "0.2-candidate"
SERIES_ID = re.compile(r"series-[0-9]{8}T[0-9]{6}Z-[a-z0-9]{8}\Z")
STATE_FIELDS = legacy.STATE_FIELDS | {"series_id"}
POPULATION_IDENTITY_FIELDS = legacy.POPULATION_IDENTITY_FIELDS + ("series_id",)
SERIES_STATE_READY = "SERIES_STATE_READY"
LEGACY_READ_ONLY = "LEGACY_READ_ONLY"
INVALID = "INVALID"


@dataclass(frozen=True)
class TemporalProbeSeriesState:
    series_id: str
    legacy_state: legacy.TemporalProbeState

    @property
    def population_identity(self) -> tuple[Any, ...]:
        return self.legacy_state.population_identity + (self.series_id,)

    def to_dict(self) -> dict[str, Any]:
        value = self.legacy_state.to_dict()
        value["state_schema_version"] = STATE_SCHEMA_VERSION
        value["series_id"] = self.series_id
        return value


@dataclass(frozen=True)
class SeriesStateValidation:
    valid: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class StateDocumentClassification:
    status: str
    readable: bool
    comparison_allowed: bool
    reason_codes: tuple[str, ...]


def create_temporal_probe_series_state(
    *,
    series_id: str,
    captured_at: datetime,
    site: str,
    service: str,
    floor: str,
    source_sort: str,
    offset: int,
    hits: int,
    content_ids: Iterable[str],
) -> TemporalProbeSeriesState:
    if not isinstance(series_id, str) or SERIES_ID.fullmatch(series_id) is None:
        raise ValueError("invalid explicit series identifier")
    base = legacy.create_temporal_probe_state(
        captured_at=captured_at,
        site=site,
        service=service,
        floor=floor,
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        content_ids=content_ids,
    )
    return TemporalProbeSeriesState(series_id, base)


def validate_temporal_probe_series_state(
    state: Any, *, as_of: datetime | None = None
) -> SeriesStateValidation:
    try:
        if not isinstance(state, TemporalProbeSeriesState):
            return SeriesStateValidation(False, ("MALFORMED_SERIES_STATE",))
        reasons = set(
            legacy.validate_temporal_probe_state(
                state.legacy_state, as_of=as_of
            ).reason_codes
        )
        if SERIES_ID.fullmatch(state.series_id) is None:
            reasons.add("INVALID_SERIES_ID")
        return SeriesStateValidation(not reasons, tuple(sorted(reasons)))
    except Exception:
        return SeriesStateValidation(False, ("INTERNAL_SERIES_STATE_ERROR",))


def serialize_temporal_probe_series_state(state: Any) -> str:
    if not validate_temporal_probe_series_state(state).valid:
        raise ValueError("invalid temporal series state")
    return json.dumps(state.to_dict(), separators=(",", ":"), sort_keys=True)


def deserialize_temporal_probe_series_state(
    value: Any,
) -> TemporalProbeSeriesState | None:
    try:
        document = json.loads(value) if isinstance(value, str) else value
        if not isinstance(document, Mapping) or set(document) != STATE_FIELDS:
            return None
        if document["state_schema_version"] != STATE_SCHEMA_VERSION:
            return None
        series_id = document["series_id"]
        legacy_document = dict(document)
        del legacy_document["series_id"]
        legacy_document["state_schema_version"] = legacy.STATE_SCHEMA_VERSION
        base = legacy.deserialize_temporal_probe_state(legacy_document)
        if base is None:
            return None
        state = TemporalProbeSeriesState(series_id, base)
        return state if validate_temporal_probe_series_state(state).valid else None
    except Exception:
        return None


def classify_temporal_state_document(value: Any) -> StateDocumentClassification:
    """Keep v0.1 readable but never silently comparable with v0.2."""

    try:
        if deserialize_temporal_probe_series_state(value) is not None:
            return StateDocumentClassification(
                SERIES_STATE_READY, True, True, ()
            )
        if legacy.deserialize_temporal_probe_state(value) is not None:
            return StateDocumentClassification(
                LEGACY_READ_ONLY,
                True,
                False,
                ("EXPLICIT_SERIES_ASSIGNMENT_REQUIRED",),
            )
        return StateDocumentClassification(
            INVALID, False, False, ("UNREADABLE_STATE_DOCUMENT",)
        )
    except Exception:
        return StateDocumentClassification(
            INVALID, False, False, ("STATE_CLASSIFICATION_ERROR",)
        )


def compare_temporal_probe_series_states(
    previous: Any, current: Any, *, as_of: datetime
) -> legacy.TemporalComparison:
    try:
        previous_validation = validate_temporal_probe_series_state(
            previous, as_of=as_of
        )
        current_validation = validate_temporal_probe_series_state(
            current, as_of=as_of
        )
        reasons = set(previous_validation.reason_codes) | set(
            current_validation.reason_codes
        )
        if reasons:
            return legacy.TemporalComparison(False, tuple(sorted(reasons)))
        if previous.series_id != current.series_id:
            return legacy.TemporalComparison(False, ("CROSS_SERIES_COMPARISON",))
        return legacy.compare_temporal_probe_states(
            previous.legacy_state, current.legacy_state, as_of=as_of
        )
    except Exception:
        return legacy.TemporalComparison(
            False, ("INTERNAL_SERIES_COMPARISON_ERROR",)
        )


__all__ = [
    "LEGACY_READ_ONLY", "POPULATION_IDENTITY_FIELDS", "SERIES_STATE_READY",
    "STATE_FIELDS", "STATE_SCHEMA_VERSION", "StateDocumentClassification",
    "TemporalProbeSeriesState", "classify_temporal_state_document",
    "compare_temporal_probe_series_states", "create_temporal_probe_series_state",
    "deserialize_temporal_probe_series_state",
    "serialize_temporal_probe_series_state", "validate_temporal_probe_series_state",
]
