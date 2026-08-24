"""Pure, plan-only retention policy for local temporal probe states.

Version 0.1 classifies safe metadata only.  It deliberately contains no
filesystem mutation or rotation executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Iterable


POLICY_VERSION = "0.1"
HOT_RETENTION_DAYS = 45
COMPARISON_POLICY = "LATEST_PREVIOUS"
ANCHOR_CANDIDATE_DAYS = (7, 30)

KEEP_HOT = "KEEP_HOT"
KEEP_LATEST = "KEEP_LATEST"
KEEP_ANCHOR_CANDIDATE = "KEEP_ANCHOR_CANDIDATE"
ELIGIBLE_FOR_FUTURE_ROTATION = "ELIGIBLE_FOR_FUTURE_ROTATION"
INVALID_IGNORE = "INVALID_IGNORE"
FUTURE_TIMESTAMP_REJECT = "FUTURE_TIMESTAMP_REJECT"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
AMBIGUOUS = "AMBIGUOUS"

KEEP_CLASSIFICATIONS = frozenset(
    {KEEP_HOT, KEEP_LATEST, KEEP_ANCHOR_CANDIDATE}
)
MANUAL_REVIEW_CLASSIFICATIONS = frozenset(
    {INVALID_IGNORE, FUTURE_TIMESTAMP_REJECT, IDENTITY_MISMATCH, AMBIGUOUS}
)
KNOWN_ISSUES = frozenset(
    {
        "MALFORMED_SCHEMA",
        "SYMLINK",
        "UNREADABLE",
        "UNKNOWN_SCHEMA_VERSION",
        "TIMESTAMP_PARSE_FAILURE",
    }
)
SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
PopulationIdentity = tuple[str, str, str, str, int, int]


@dataclass(frozen=True)
class StateMetadata:
    filename: str
    population_identity: PopulationIdentity | None
    captured_at: datetime | None
    sha256: str | None
    valid: bool
    issue_code: str | None = None


@dataclass(frozen=True)
class StateClassification:
    filename: str
    classification: str
    anchor_days: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PopulationSummary:
    site: str
    service: str
    floor: str
    source_sort: str
    offset: int
    hits: int
    total_states: int
    keep_count: int
    future_rotation_candidate_count: int
    manual_review_count: int

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RetentionPlan:
    success: bool
    reason_code: str | None
    policy_version: str
    generated_at: str
    total_states: int
    keep_count: int
    future_rotation_candidate_count: int
    manual_review_count: int
    comparison_policy: str
    hot_retention_days: int
    anchor_candidate_days: tuple[int, ...]
    population_summaries: tuple[PopulationSummary, ...]
    states: tuple[StateClassification, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                key: value
                for key, value in self.__dict__.items()
                if key not in {"population_summaries", "states"}
            },
            "anchor_candidate_days": list(self.anchor_candidate_days),
            "population_summaries": [
                value.to_dict() for value in self.population_summaries
            ],
            "states": [value.to_dict() for value in self.states],
        }


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _aware(value: Any) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _valid_identity(value: Any) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 6
        and all(isinstance(part, str) and part for part in value[:4])
        and all(isinstance(part, int) and not isinstance(part, bool) and part > 0 for part in value[4:])
    )


def _safe_basename(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "invalid-state"
    name = Path(value).name
    if SAFE_FILENAME.fullmatch(name) is None:
        return "invalid-state"
    return name


def _metadata_valid(value: Any) -> bool:
    return (
        isinstance(value, StateMetadata)
        and value.valid is True
        and value.issue_code is None
        and _valid_identity(value.population_identity)
        and _aware(value.captured_at)
        and isinstance(value.sha256, str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", value.sha256) is not None
        and _safe_basename(value.filename) == value.filename
    )


def _failure(generated_at: Any) -> RetentionPlan:
    timestamp = _timestamp(generated_at) if _aware(generated_at) else ""
    return RetentionPlan(
        False,
        "INTERNAL_RETENTION_ERROR",
        POLICY_VERSION,
        timestamp,
        0,
        0,
        0,
        0,
        COMPARISON_POLICY,
        HOT_RETENTION_DAYS,
        ANCHOR_CANDIDATE_DAYS,
        (),
        (),
    )


def plan_retention(
    metadata: Iterable[StateMetadata],
    *,
    generated_at: datetime,
    allowed_populations: frozenset[PopulationIdentity] | None = None,
) -> RetentionPlan:
    """Classify metadata without reading, writing, moving, or removing files."""

    try:
        if not _aware(generated_at):
            return _failure(generated_at)
        values = tuple(metadata)
        if allowed_populations is not None and (
            not isinstance(allowed_populations, frozenset)
            or any(not _valid_identity(value) for value in allowed_populations)
        ):
            return _failure(generated_at)

        prelim: dict[int, str] = {}
        valid_indexes: list[int] = []
        by_identity: dict[PopulationIdentity, list[int]] = {}
        for index, value in enumerate(values):
            if not isinstance(value, StateMetadata) or not _metadata_valid(value):
                prelim[index] = INVALID_IGNORE
                continue
            identity = value.population_identity
            captured_at = value.captured_at
            if identity is None or captured_at is None:
                prelim[index] = INVALID_IGNORE
            elif captured_at > generated_at:
                prelim[index] = FUTURE_TIMESTAMP_REJECT
            elif allowed_populations is not None and identity not in allowed_populations:
                prelim[index] = IDENTITY_MISMATCH
            else:
                valid_indexes.append(index)
                by_identity.setdefault(identity, []).append(index)

        ambiguous: set[int] = set()
        for indexes in by_identity.values():
            timestamps: dict[datetime, list[int]] = {}
            for index in indexes:
                captured_at = values[index].captured_at
                if captured_at is not None:
                    timestamps.setdefault(captured_at, []).append(index)
            for duplicates in timestamps.values():
                hashes = {values[index].sha256.lower() for index in duplicates if values[index].sha256}
                if len(hashes) > 1:
                    ambiguous.update(duplicates)
        for index in ambiguous:
            prelim[index] = AMBIGUOUS

        classifications: dict[int, StateClassification] = {}
        for index, classification in prelim.items():
            classifications[index] = StateClassification(
                _safe_basename(getattr(values[index], "filename", None)),
                classification,
            )

        for identity, indexes in by_identity.items():
            eligible = [index for index in indexes if index not in ambiguous]
            if not eligible:
                continue
            latest_at = max(values[index].captured_at for index in eligible)
            anchor_targets = {
                latest_at - timedelta(days=days): days
                for days in ANCHOR_CANDIDATE_DAYS
            }
            for index in eligible:
                value = values[index]
                captured_at = value.captured_at
                anchor_days = anchor_targets.get(captured_at)
                age = generated_at - captured_at
                if anchor_days is not None:
                    classification = KEEP_ANCHOR_CANDIDATE
                elif age <= timedelta(days=HOT_RETENTION_DAYS):
                    classification = KEEP_HOT
                elif captured_at == latest_at:
                    classification = KEEP_LATEST
                else:
                    classification = ELIGIBLE_FOR_FUTURE_ROTATION
                classifications[index] = StateClassification(
                    _safe_basename(value.filename), classification, anchor_days
                )

        ordered = tuple(classifications[index] for index in range(len(values)))
        population_results: list[PopulationSummary] = []
        for identity in sorted(by_identity):
            indexes = by_identity[identity]
            selected = [classifications[index] for index in indexes]
            population_results.append(
                PopulationSummary(
                    *identity,
                    total_states=len(selected),
                    keep_count=sum(value.classification in KEEP_CLASSIFICATIONS for value in selected),
                    future_rotation_candidate_count=sum(value.classification == ELIGIBLE_FOR_FUTURE_ROTATION for value in selected),
                    manual_review_count=sum(value.classification in MANUAL_REVIEW_CLASSIFICATIONS for value in selected),
                )
            )
        return RetentionPlan(
            True,
            None,
            POLICY_VERSION,
            _timestamp(generated_at),
            len(values),
            sum(value.classification in KEEP_CLASSIFICATIONS for value in ordered),
            sum(value.classification == ELIGIBLE_FOR_FUTURE_ROTATION for value in ordered),
            sum(value.classification in MANUAL_REVIEW_CLASSIFICATIONS for value in ordered),
            COMPARISON_POLICY,
            HOT_RETENTION_DAYS,
            ANCHOR_CANDIDATE_DAYS,
            tuple(population_results),
            ordered,
        )
    except Exception:
        return _failure(generated_at)


__all__ = [
    "AMBIGUOUS",
    "ANCHOR_CANDIDATE_DAYS",
    "COMPARISON_POLICY",
    "ELIGIBLE_FOR_FUTURE_ROTATION",
    "FUTURE_TIMESTAMP_REJECT",
    "HOT_RETENTION_DAYS",
    "IDENTITY_MISMATCH",
    "INVALID_IGNORE",
    "KEEP_ANCHOR_CANDIDATE",
    "KEEP_HOT",
    "KEEP_LATEST",
    "POLICY_VERSION",
    "RetentionPlan",
    "StateClassification",
    "StateMetadata",
    "plan_retention",
]
