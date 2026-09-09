"""Memory-only evidence for v0.2 filename and identity boundaries."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import temporal_probe_series_state as series
import temporal_probe_series_state_store_candidate as store

VERSION = "0.1"
EVIDENCE_READY = "SERIES_FILENAME_IDENTITY_VERIFIED"
BLOCKED = "BLOCKED"
BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_A = "series-20260909T000000Z-a1b2c3d4"
SERIES_B = "series-20260910T000000Z-b1c2d3e4"


@dataclass(frozen=True)
class FilenameIdentityEvidence:
    version: str
    status: str
    success: bool
    deterministic_plan_verified: bool
    series_filename_boundary_verified: bool
    population_filename_boundary_verified: bool
    timestamp_filename_boundary_verified: bool
    same_identity_conflict_signal_verified: bool
    comparison_identity_includes_series: bool
    raw_series_id_exposed: bool
    filesystem_access_performed: bool
    state_write_authorized: bool
    checks_passed: int
    checks_required: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _state(series_id=SERIES_A, captured_at=BASE, source_sort="rank",
           offset=1, content_ids=("fixture-1",)):
    return series.create_temporal_probe_series_state(
        series_id=series_id, captured_at=captured_at, site="FANZA",
        service="digital", floor="videoa", source_sort=source_sort,
        offset=offset, hits=100, content_ids=content_ids,
    )


def assess_filename_identity() -> FilenameIdentityEvidence:
    """Exercise identity variants without returning filenames or digests."""
    try:
        baseline_state = _state()
        same = store.plan_series_state_write(baseline_state, as_of=AS_OF)
        repeated = store.plan_series_state_write(baseline_state, as_of=AS_OF)
        other_series_state = _state(series_id=SERIES_B)
        other_series = store.plan_series_state_write(
            other_series_state, as_of=AS_OF
        )
        other_population = store.plan_series_state_write(
            _state(source_sort="review", offset=101), as_of=AS_OF
        )
        other_time = store.plan_series_state_write(
            _state(captured_at=BASE + timedelta(days=1)), as_of=AS_OF
        )
        other_content = store.plan_series_state_write(
            _state(content_ids=("fixture-2",)), as_of=AS_OF
        )
        plans = (same, repeated, other_series, other_population,
                 other_time, other_content)
        ready_plans = all(
            item.success and item.status == store.WRITE_PLAN_READY
            and item.series_aware_identity
            and not item.filesystem_access_performed
            and not item.state_write_authorized
            for item in plans
        )
        checks = (
            ready_plans,
            same.filename == repeated.filename
            and same.document_sha256 == repeated.document_sha256,
            same.filename != other_series.filename,
            same.filename != other_population.filename,
            same.filename != other_time.filename,
            same.filename == other_content.filename
            and same.document_sha256 != other_content.document_sha256,
            baseline_state.population_identity
            != other_series_state.population_identity,
            SERIES_A not in (same.filename or "")
            and SERIES_B not in (other_series.filename or ""),
        )
        passed = sum(value is True for value in checks)
        success = passed == len(checks)
        return FilenameIdentityEvidence(
            VERSION, EVIDENCE_READY if success else BLOCKED, success,
            checks[1], checks[2], checks[3], checks[4], checks[5], checks[6],
            not checks[7], False, False, passed, len(checks),
            ("SERIES_FILENAME_AND_IDENTITY_BOUNDARIES_VERIFIED",)
            if success else ("SERIES_FILENAME_IDENTITY_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return FilenameIdentityEvidence(
            VERSION, BLOCKED, False, False, False, False, False, False,
            False, False, False, False, 0, 8,
            ("SERIES_FILENAME_IDENTITY_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_filename_identity()
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status == EVIDENCE_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
