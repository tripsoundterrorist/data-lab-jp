"""Pure temporal probe state creation, validation, and comparison.

The module never writes files. Raw source identifiers are accepted only by the
in-memory factory and are replaced with probe-specific pseudonymous IDs. These
IDs are local-only comparison tokens, not Public IDs or publication-safe IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


STATE_SCHEMA_VERSION = "0.1"
ANONYMOUS_ID_NAMESPACE = "data-lab-temporal-probe-item-v0.1"
STATE_FIELDS = frozenset(
    {
        "state_schema_version",
        "captured_at",
        "site",
        "service",
        "floor",
        "source_sort",
        "offset",
        "hits",
        "returned_count",
        "anonymous_item_ids",
    }
)
POPULATION_IDENTITY_FIELDS = (
    "site",
    "service",
    "floor",
    "source_sort",
    "offset",
    "hits",
)
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SAFE_CONTENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
ANONYMOUS_ID = re.compile(r"prb_[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class TemporalProbeState:
    state_schema_version: str
    captured_at: datetime
    site: str
    service: str
    floor: str
    source_sort: str
    offset: int
    hits: int
    returned_count: int
    anonymous_item_ids: tuple[str, ...]

    @property
    def population_identity(self) -> tuple[str, str, str, str, int, int]:
        return (
            self.site,
            self.service,
            self.floor,
            self.source_sort,
            self.offset,
            self.hits,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_schema_version": self.state_schema_version,
            "captured_at": self.captured_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "site": self.site,
            "service": self.service,
            "floor": self.floor,
            "source_sort": self.source_sort,
            "offset": self.offset,
            "hits": self.hits,
            "returned_count": self.returned_count,
            "anonymous_item_ids": list(self.anonymous_item_ids),
        }


@dataclass(frozen=True)
class StateValidation:
    valid: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class TemporalComparison:
    comparison_valid: bool
    reason_codes: tuple[str, ...]
    previous_count: int | None = None
    current_count: int | None = None
    retained_count: int | None = None
    entered_count: int | None = None
    exited_count: int | None = None
    retention_rate: float | None = None
    entry_rate: float | None = None
    exit_rate: float | None = None
    turnover_rate: float | None = None
    jaccard: float | None = None


def _aware(value: Any) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _safe_component(value: Any) -> bool:
    return isinstance(value, str) and SAFE_COMPONENT.fullmatch(value) is not None


def anonymous_probe_item_id(
    content_id: str,
    *,
    site: str,
    service: str,
    floor: str,
    source_sort: str,
) -> str:
    """Create a namespaced pseudonymous ID without credentials or item data."""

    if not SAFE_CONTENT_ID.fullmatch(content_id):
        raise ValueError("invalid source identifier")
    if not all(_safe_component(value) for value in (site, service, floor)):
        raise ValueError("invalid population component")
    if source_sort not in {"rank", "review"}:
        raise ValueError("unsupported temporal population")
    source = "\0".join(
        (
            ANONYMOUS_ID_NAMESPACE,
            site,
            service,
            floor,
            source_sort,
            content_id,
        )
    )
    return "prb_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]


def create_temporal_probe_state(
    *,
    captured_at: datetime,
    site: str,
    service: str,
    floor: str,
    source_sort: str,
    offset: int,
    hits: int,
    content_ids: Iterable[str],
) -> TemporalProbeState:
    anonymous_ids = tuple(
        sorted(
            anonymous_probe_item_id(
                content_id,
                site=site,
                service=service,
                floor=floor,
                source_sort=source_sort,
            )
            for content_id in content_ids
        )
    )
    state = TemporalProbeState(
        state_schema_version=STATE_SCHEMA_VERSION,
        captured_at=captured_at,
        site=site,
        service=service,
        floor=floor,
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        returned_count=len(anonymous_ids),
        anonymous_item_ids=anonymous_ids,
    )
    validation = validate_temporal_probe_state(state)
    if not validation.valid:
        raise ValueError("invalid temporal probe state")
    return state


def validate_temporal_probe_state(
    state: Any, *, as_of: datetime | None = None
) -> StateValidation:
    reasons: set[str] = set()
    try:
        if not isinstance(state, TemporalProbeState):
            return StateValidation(False, ("MALFORMED_STATE",))
        if state.state_schema_version != STATE_SCHEMA_VERSION:
            reasons.add("UNKNOWN_SCHEMA_VERSION")
        if not _aware(state.captured_at):
            reasons.add("INVALID_TIMESTAMP")
        if as_of is not None:
            if not _aware(as_of) or not _aware(state.captured_at):
                reasons.add("INVALID_TIMESTAMP")
            elif state.captured_at.astimezone(timezone.utc) > as_of.astimezone(
                timezone.utc
            ):
                reasons.add("FUTURE_TIMESTAMP")
        if not all(
            _safe_component(value) for value in (state.site, state.service, state.floor)
        ):
            reasons.add("INVALID_POPULATION_IDENTITY")
        if state.source_sort not in {"rank", "review"}:
            reasons.add("UNKNOWN_SORT")
        if (
            isinstance(state.offset, bool)
            or not isinstance(state.offset, int)
            or state.offset <= 0
            or isinstance(state.hits, bool)
            or not isinstance(state.hits, int)
            or state.hits <= 0
        ):
            reasons.add("INVALID_POPULATION_IDENTITY")
        if not isinstance(state.anonymous_item_ids, tuple):
            reasons.add("MALFORMED_ANONYMOUS_IDS")
        else:
            if any(
                not isinstance(value, str) or ANONYMOUS_ID.fullmatch(value) is None
                for value in state.anonymous_item_ids
            ):
                reasons.add("MALFORMED_ANONYMOUS_IDS")
            if len(set(state.anonymous_item_ids)) != len(state.anonymous_item_ids):
                reasons.add("DUPLICATE_ANONYMOUS_ID")
        if (
            isinstance(state.returned_count, bool)
            or not isinstance(state.returned_count, int)
            or state.returned_count < 0
            or state.returned_count != len(state.anonymous_item_ids)
            or state.returned_count > state.hits
        ):
            reasons.add("COUNT_MISMATCH")
        return StateValidation(not reasons, tuple(sorted(reasons)))
    except Exception:
        return StateValidation(False, ("INTERNAL_STATE_ERROR",))


def serialize_temporal_probe_state(state: Any) -> str:
    validation = validate_temporal_probe_state(state)
    if not validation.valid:
        raise ValueError("invalid temporal probe state")
    return json.dumps(state.to_dict(), separators=(",", ":"), sort_keys=True)


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if _aware(parsed) else None


def deserialize_temporal_probe_state(value: Any) -> TemporalProbeState | None:
    try:
        document = json.loads(value) if isinstance(value, str) else value
        if not isinstance(document, Mapping) or set(document) != STATE_FIELDS:
            return None
        identifiers = document["anonymous_item_ids"]
        if not isinstance(identifiers, list):
            return None
        state = TemporalProbeState(
            state_schema_version=document["state_schema_version"],
            captured_at=parse_timestamp(document["captured_at"]),  # type: ignore[arg-type]
            site=document["site"],
            service=document["service"],
            floor=document["floor"],
            source_sort=document["source_sort"],
            offset=document["offset"],
            hits=document["hits"],
            returned_count=document["returned_count"],
            anonymous_item_ids=tuple(identifiers),
        )
        return state if validate_temporal_probe_state(state).valid else None
    except Exception:
        return None


def _rate(numerator: int, denominator: int, *, empty_value: float = 0.0) -> float:
    return round(numerator / denominator, 6) if denominator else empty_value


def _compare_validated(
    previous: TemporalProbeState, current: TemporalProbeState
) -> TemporalComparison:
    previous_ids = set(previous.anonymous_item_ids)
    current_ids = set(current.anonymous_item_ids)
    retained = previous_ids & current_ids
    entered = current_ids - previous_ids
    exited = previous_ids - current_ids
    union = previous_ids | current_ids
    return TemporalComparison(
        comparison_valid=True,
        reason_codes=(),
        previous_count=len(previous_ids),
        current_count=len(current_ids),
        retained_count=len(retained),
        entered_count=len(entered),
        exited_count=len(exited),
        retention_rate=_rate(len(retained), len(previous_ids), empty_value=1.0),
        entry_rate=_rate(len(entered), len(current_ids)),
        exit_rate=_rate(len(exited), len(previous_ids)),
        turnover_rate=_rate(len(entered) + len(exited), len(union)),
        jaccard=_rate(len(retained), len(union), empty_value=1.0),
    )


def compare_temporal_probe_states(
    previous: Any, current: Any, *, as_of: datetime
) -> TemporalComparison:
    try:
        previous_validation = validate_temporal_probe_state(previous, as_of=as_of)
        current_validation = validate_temporal_probe_state(current, as_of=as_of)
        reasons = set(previous_validation.reason_codes) | set(
            current_validation.reason_codes
        )
        if reasons:
            return TemporalComparison(False, tuple(sorted(reasons)))
        if previous.population_identity != current.population_identity:
            return TemporalComparison(False, ("POPULATION_IDENTITY_MISMATCH",))
        if current.captured_at.astimezone(timezone.utc) <= previous.captured_at.astimezone(
            timezone.utc
        ):
            return TemporalComparison(False, ("NON_INCREASING_TIMESTAMP",))
        return _compare_validated(previous, current)
    except Exception:
        return TemporalComparison(False, ("INTERNAL_COMPARISON_ERROR",))


__all__ = [
    "ANONYMOUS_ID_NAMESPACE",
    "POPULATION_IDENTITY_FIELDS",
    "STATE_SCHEMA_VERSION",
    "StateValidation",
    "TemporalComparison",
    "TemporalProbeState",
    "anonymous_probe_item_id",
    "compare_temporal_probe_states",
    "create_temporal_probe_state",
    "deserialize_temporal_probe_state",
    "serialize_temporal_probe_state",
    "validate_temporal_probe_state",
]
