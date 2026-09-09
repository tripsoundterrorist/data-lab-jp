"""Memory-only evidence that legacy temporal states remain read-only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import temporal_probe_series_discovery as discovery
import temporal_probe_series_state as series
import temporal_probe_state as legacy


VERSION = "0.1"
EVIDENCE_READY = "LEGACY_READ_ONLY_DISCOVERY_VERIFIED"
BLOCKED = "BLOCKED"
BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_A = "series-20260909T000000Z-a1b2c3d4"
SERIES_B = "series-20260910T000000Z-b1c2d3e4"


@dataclass(frozen=True)
class LegacyDiscoveryEvidence:
    version: str
    status: str
    success: bool
    legacy_readable: bool
    legacy_comparison_allowed: bool
    same_series_selection_verified: bool
    legacy_exclusion_verified: bool
    cross_series_exclusion_verified: bool
    legacy_migration_authorized: bool
    state_write_authorized: bool
    checks_passed: int
    checks_required: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _legacy_document() -> str:
    state = legacy.create_temporal_probe_state(
        captured_at=BASE,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort="rank",
        offset=1,
        hits=100,
        content_ids=("fixture-legacy",),
    )
    return legacy.serialize_temporal_probe_state(state)


def _series_state(
    captured_at: datetime, *, series_id: str = SERIES_A
) -> series.TemporalProbeSeriesState:
    return series.create_temporal_probe_series_state(
        series_id=series_id,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort="rank",
        offset=1,
        hits=100,
        content_ids=("fixture-series",),
    )


def assess_legacy_read_only_discovery() -> LegacyDiscoveryEvidence:
    """Exercise mixed documents without filesystem discovery or persistence."""

    try:
        legacy_document = _legacy_document()
        classified = series.classify_temporal_state_document(legacy_document)
        current = _series_state(BASE + timedelta(days=3))
        previous = _series_state(BASE + timedelta(days=2))
        cross = _series_state(BASE + timedelta(days=1), series_id=SERIES_B)
        mixed = discovery.discover_latest_same_series(
            current,
            (
                legacy_document,
                series.serialize_temporal_probe_series_state(cross),
                series.serialize_temporal_probe_series_state(previous),
            ),
            as_of=AS_OF,
        )
        legacy_only = discovery.discover_latest_same_series(
            current, (legacy_document,), as_of=AS_OF
        )
        checks = (
            classified.status == series.LEGACY_READ_ONLY,
            classified.readable and not classified.comparison_allowed,
            series.deserialize_temporal_probe_series_state(legacy_document) is None,
            mixed.status == discovery.LATEST_FOUND
            and mixed.selected == previous,
            mixed.legacy_excluded_count == 1,
            mixed.cross_series_excluded_count == 1,
            legacy_only.status == discovery.EXPLICIT_BASELINE_CANDIDATE
            and legacy_only.legacy_excluded_count == 1
            and not legacy_only.comparison_candidate,
        )
        passed = sum(value is True for value in checks)
        ready = passed == len(checks)
        return LegacyDiscoveryEvidence(
            VERSION,
            EVIDENCE_READY if ready else BLOCKED,
            ready,
            classified.readable is True,
            classified.comparison_allowed is True,
            checks[3] is True,
            checks[4] is True and checks[6] is True,
            checks[5] is True,
            False,
            False,
            passed,
            len(checks),
            (
                "LEGACY_DOCUMENTS_READ_ONLY_AND_EXCLUDED",
                "SAME_SERIES_SELECTION_ONLY",
            ) if ready else ("LEGACY_DISCOVERY_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return LegacyDiscoveryEvidence(
            VERSION, BLOCKED, False, False, False, False, False, False,
            False, False, 0, 7, ("LEGACY_DISCOVERY_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_legacy_read_only_discovery()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == EVIDENCE_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
