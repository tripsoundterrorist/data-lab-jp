"""Offline, snapshot-bound price-display release review; never executes release."""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import sqlite3

import revenue_mvp_price_label_correction as labels
import revenue_mvp_price_display_transition as transition


@dataclass(frozen=True)
class DisplayReleaseReview:
    status: str
    reason_code: str
    candidate_sha256: str | None = None
    lower_bound_label_count: int = 0
    display_match_observed: bool = False
    current_eligibility_verified: bool = False
    publication_allowed: bool = False
    database_write_performed: bool = False
    historical_evidence_modified: bool = False
    explicit_release_approval_required: bool = True

    def to_dict(self):
        return asdict(self)


def assess(baseline, candidate, database: Path, expected_database_sha256,
           historical_surface_evidence, *, observation=None, evaluated_at=None):
    """Bind exact label delta to saved raw prices without refreshing their date.

    A saved snapshot proves label semantics, not current sale eligibility.
    No API, HTTP capture, file output, D1 write or approval consumption occurs.
    """
    def blocked(reason):
        return DisplayReleaseReview("BLOCKED", reason)
    try:
        display = transition.review(baseline, candidate, historical_surface_evidence,
                                    observation=observation, evaluated_at=evaluated_at)
        if display.status == "BLOCKED":
            return blocked(display.reason_code)
        if (database.is_symlink()
                or sha256(database.read_bytes()).hexdigest() != expected_database_sha256):
            return blocked("PRICE_DATABASE_IDENTITY_INVALID")
        old, new = transition.canonical(baseline), transition.canonical(candidate)
        if transition.canonical(labels.correct(old, database)) != new:
            return blocked("PRICE_RAW_PROVENANCE_MISMATCH")
        if sha256(database.read_bytes()).hexdigest() != expected_database_sha256:
            return blocked("PRICE_DATABASE_CHANGED")
        return DisplayReleaseReview(
            "DISPLAY_MATCH_REQUIRES_CURRENT_ELIGIBILITY_REVIEW"
                if display.current_display_match_observed
                else "DISPLAY_CANDIDATE_READY_FOR_SEPARATE_RELEASE_REVIEW",
            "SAVED_PRICE_SEMANTICS_ONLY_NOT_CURRENT_ELIGIBILITY_OR_APPROVAL",
            display.candidate_sha256, new.count('円〜</p>'.encode()),
            display.current_display_match_observed,
        )
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError, sqlite3.Error):
        return blocked("DISPLAY_RELEASE_INPUT_INVALID")
