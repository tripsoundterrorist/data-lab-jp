"""Aggregate-only manual COMPLIANCE packet for the 300-item expansion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_MANUAL_COMPLIANCE_DECISION"
BLOCKED = "BLOCKED_PENDING_EXPANSION_EVIDENCE"
FAIL_CLOSED = "COMPLIANCE_PACKET_FAIL_CLOSED"
ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_RESPONSE = ROOT / "runtime" / "evidence" / "revenue-mvp-official-response-20260916.json"
COVERAGE_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-final-runtime-coverage-20261002.json"
SEO_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-seo-quality-20261001.json"
FUNNEL_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-product-funnel-window-20261001.json"
FUNNEL_REVIEW_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-product-funnel-review.json"
TARGET_COUNT = 300
REQUIRED_LIFECYCLE_CONFIRMATIONS = frozenset({
    "CID_ZERO_RESULT_MEANING",
    "API_VISIBLE_MEANING",
    "API_INVISIBLE_MEANING",
    "AFFILIATE_URL_PRESENCE_MEANING",
    "AFFILIATE_URL_ABSENCE_MEANING",
    "PERIODIC_REQUERY_RECOMMENDATION",
    "NONVISIBLE_PAGE_HANDLING",
    "NONVISIBLE_LINK_HANDLING",
})


def _reviewed_on_valid(value: Any) -> bool:
    if type(value) is not str:
        return False
    try:
        return date.fromisoformat(value) >= date(2026, 10, 10)
    except ValueError:
        return False


@dataclass(frozen=True)
class ExpansionCompliancePacket:
    version: str
    status: str
    target_item_count: int
    official_lifecycle_core_confirmed: bool
    candidate_lookup_ready_count: int
    candidate_redirect_ready_count: int
    candidate_runtime_ready_count: int
    presentation_policy_verified: bool
    product_funnel_window_closed: bool
    product_funnel_review_completed: bool
    compliance_publication_confirmed: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]
    required_manual_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["required_manual_checks"] = list(self.required_manual_checks)
        return value


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_packet(
    official: Any,
    coverage: Any,
    seo: Any,
    funnel: Any,
    funnel_review: Any,
) -> ExpansionCompliancePacket:
    try:
        if type(official) is not list or len(official) < 1:
            raise ValueError
        lifecycle_entries = [
            entry for entry in official
            if type(entry) is dict
            and entry.get("referenced_blocker") == "DMM_LIFECYCLE_AVAILABILITY"
        ]
        if len(lifecycle_entries) != 1:
            raise ValueError
        lifecycle = lifecycle_entries[0]
        confirmed = set(lifecycle.get("explicit_confirmations", []))
        official_core = (
            lifecycle.get("source_type") == "DIRECT_SUPPORT_CONFIRMATION"
            and lifecycle.get("source_authority") == "DMM_AFFILIATE_SUPPORT"
            and not lifecycle.get("ambiguity_flags")
            and REQUIRED_LIFECYCLE_CONFIRMATIONS <= confirmed
        )
        if (
            type(coverage) is not dict or type(seo) is not dict
            or type(funnel) is not dict or type(funnel_review) is not dict
        ):
            raise ValueError
        lookup = coverage.get("candidate_lookup_ready_count")
        redirects = coverage.get("candidate_redirect_ready_count")
        runtime = coverage.get("candidate_runtime_revalidation_ready_count")
        coverage_verified = (
            coverage.get("version") == "0.1"
            and coverage.get("status") == "FINAL_RUNTIME_COVERAGE_VERIFIED"
            and coverage.get("target_item_count") == TARGET_COUNT
            and coverage.get("initial_remaining_count") == 0
            and coverage.get("retry_waiting_count") == 0
            and coverage.get("legacy_pending_review_count") == 0
            and coverage.get("publication_allowed") is False
            and coverage.get("production_write_allowed") is False
            and coverage.get("deployment_allowed") is False
            and type(coverage.get("postwrite_d1_snapshot_sha256")) is str
            and len(coverage["postwrite_d1_snapshot_sha256"]) == 64
        )
        if any(type(value) is not int or not 0 <= value <= TARGET_COUNT
               for value in (lookup, redirects, runtime)) or not coverage_verified:
            raise ValueError
        presentation = (
            seo.get("status") == "SEO_QUALITY_REVIEWED_KEEP_NOINDEX"
            and seo.get("complete_card_count") == 100
            and seo.get("unique_cta_route_count") == 100
            and seo.get("indexing_allowed") is False
            and seo.get("detail_page_generation_allowed") is False
            and seo.get("publication_allowed") is False
        )
        funnel_closed = funnel.get("product_funnel_window_closed") is True
        funnel_review_completed = (
            funnel_review.get("status") == "PRODUCT_FUNNEL_REVIEW_COMPLETED"
            and funnel_review.get("period_start") == "2026-10-02"
            and funnel_review.get("period_end") == "2026-10-08"
            and _reviewed_on_valid(funnel_review.get("reviewed_on"))
            and funnel_review.get("product_funnel_review_completed") is True
            and funnel_review.get("expansion_decision_allowed") is False
            and funnel_review.get("production_write_allowed") is False
            and funnel_review.get("external_write_performed") is False
            and funnel_review.get("reason_codes") == []
        )
    except (TypeError, ValueError, KeyError):
        return ExpansionCompliancePacket(
            VERSION, FAIL_CLOSED, TARGET_COUNT, False, 0, 0, 0, False,
            False, False, False, False, False, ("COMPLIANCE_EVIDENCE_INVALID",),
            ("REBUILD_SANITIZED_EVIDENCE_PACKET",),
        )

    reasons: set[str] = set()
    if not official_core:
        reasons.add("OFFICIAL_LIFECYCLE_CORE_UNCONFIRMED")
    if lookup != TARGET_COUNT:
        reasons.add("LOOKUP_COVERAGE_INCOMPLETE")
    if redirects != TARGET_COUNT:
        reasons.add("REDIRECT_COVERAGE_INCOMPLETE")
    if runtime != TARGET_COUNT:
        reasons.add("RUNTIME_ELIGIBILITY_INCOMPLETE")
    if not presentation:
        reasons.add("PRESENTATION_POLICY_UNVERIFIED")
    if not funnel_closed:
        reasons.add("PRODUCT_FUNNEL_WINDOW_OPEN")
    if not funnel_review_completed:
        reasons.add("PRODUCT_FUNNEL_REVIEW_INCOMPLETE")

    ready = not reasons
    return ExpansionCompliancePacket(
        VERSION,
        READY if ready else BLOCKED,
        TARGET_COUNT,
        official_core,
        lookup,
        redirects,
        runtime,
        presentation,
        funnel_closed,
        funnel_review_completed,
        False,
        False,
        False,
        tuple(sorted(reasons)),
        (
            "CONFIRM_UNEXPECTED_CLOUDFLARE_CRON_REMOVED_OR_ACCOUNTED_FOR",
            "CONFIRM_EXACT_300_RUNTIME_ELIGIBILITY",
            "CONFIRM_API_UNAVAILABLE_AND_AFFILIATE_INELIGIBLE_ITEMS_EXCLUDED",
            "CONFIRM_PR_DISCLOSURE_AND_OPAQUE_FIRST_PARTY_ROUTE_UNCHANGED",
            "RECORD_EXPLICIT_MANUAL_COMPLIANCE_DECISION",
        ),
    )


def current_packet() -> ExpansionCompliancePacket:
    try:
        try:
            funnel_review = _load(FUNNEL_REVIEW_EVIDENCE)
        except (OSError, UnicodeError, json.JSONDecodeError):
            funnel_review = {}
        return build_packet(
            _load(OFFICIAL_RESPONSE), _load(COVERAGE_EVIDENCE),
            _load(SEO_EVIDENCE), _load(FUNNEL_EVIDENCE),
            funnel_review,
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return build_packet(None, None, None, None, None)


def main() -> int:
    result = current_packet()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
