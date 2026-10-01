"""Pure readiness gate for a staged Revenue MVP public-catalog expansion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


VERSION = "0.1"
CURRENT_PUBLIC_ITEM_COUNT = 100
NEXT_STAGE_ITEM_COUNT = 300
READY_FOR_MANUAL_EXPANSION_REVIEW = "READY_FOR_MANUAL_EXPANSION_REVIEW"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
ROOT = Path(__file__).resolve().parents[1]
COLLECTION_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-collection-20261001.json"
D1_COVERAGE_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-initial-batch-000-live-success-20261001.json"
SITEMAP_CAPACITY_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-sitemap-capacity-20261001.json"
ROLLBACK_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-rollback-rehearsal-20261001.json"
SEO_QUALITY_EVIDENCE = ROOT / "runtime" / "evidence" / "revenue-mvp-expansion-seo-quality-20261001.json"


@dataclass(frozen=True)
class ExpansionEvidence:
    current_public_item_count: int
    target_public_item_count: int
    candidate_unique_item_count: int
    eligible_item_count: int
    image_ready_count: int
    price_ready_count: int
    fresh_item_count: int
    affiliate_lookup_ready_count: int
    affiliate_redirect_ready_count: int
    runtime_revalidation_ready_count: int
    existing_surface_preservation_verified: bool
    sitemap_capacity_verified: bool
    seo_quality_reviewed: bool
    cloudflare_free_plan_capacity_verified: bool
    compliance_publication_confirmed: bool
    product_funnel_window_closed: bool
    rollback_plan_verified: bool


@dataclass(frozen=True)
class ExpansionReadiness:
    version: str
    status: str
    manual_expansion_review_candidate: bool
    publication_allowed: bool
    production_write_allowed: bool
    deployment_allowed: bool
    current_public_item_count: int
    target_public_item_count: int
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def _result(
    status: str,
    current_count: int,
    target_count: int,
    reasons: tuple[str, ...],
    actions: tuple[str, ...],
) -> ExpansionReadiness:
    ready = status == READY_FOR_MANUAL_EXPANSION_REVIEW
    return ExpansionReadiness(
        VERSION,
        status,
        ready,
        False,
        False,
        False,
        current_count,
        target_count,
        reasons,
        actions,
    )


def assess(evidence: Any) -> ExpansionReadiness:
    if not isinstance(evidence, ExpansionEvidence):
        return _result(
            FAIL_CLOSED, 0, 0, ("EVIDENCE_INVALID",),
            ("PROVIDE_TYPED_CURRENT_EVIDENCE",),
        )

    count_fields = (
        "current_public_item_count",
        "target_public_item_count",
        "candidate_unique_item_count",
        "eligible_item_count",
        "image_ready_count",
        "price_ready_count",
        "fresh_item_count",
        "affiliate_lookup_ready_count",
        "affiliate_redirect_ready_count",
        "runtime_revalidation_ready_count",
    )
    bool_fields = tuple(
        field for field in ExpansionEvidence.__dataclass_fields__
        if field not in count_fields
    )
    if any(type(getattr(evidence, field)) is not int for field in count_fields) or any(
        type(getattr(evidence, field)) is not bool for field in bool_fields
    ) or any(getattr(evidence, field) < 0 for field in count_fields):
        return _result(
            FAIL_CLOSED,
            evidence.current_public_item_count
            if type(evidence.current_public_item_count) is int else 0,
            evidence.target_public_item_count
            if type(evidence.target_public_item_count) is int else 0,
            ("EVIDENCE_INVALID",),
            ("PROVIDE_TYPED_CURRENT_EVIDENCE",),
        )

    reasons: set[str] = set()
    if evidence.current_public_item_count != CURRENT_PUBLIC_ITEM_COUNT:
        reasons.add("CURRENT_PUBLIC_SURFACE_NOT_EXACT")
    if evidence.target_public_item_count != NEXT_STAGE_ITEM_COUNT:
        reasons.add("TARGET_STAGE_INVALID")

    exact_count_checks = {
        "CANDIDATE_SET_NOT_EXACT": evidence.candidate_unique_item_count,
        "ELIGIBILITY_NOT_EXACT": evidence.eligible_item_count,
        "IMAGE_COVERAGE_NOT_EXACT": evidence.image_ready_count,
        "PRICE_COVERAGE_NOT_EXACT": evidence.price_ready_count,
        "FRESHNESS_NOT_EXACT": evidence.fresh_item_count,
        "AFFILIATE_LOOKUP_NOT_EXACT": evidence.affiliate_lookup_ready_count,
        "AFFILIATE_REDIRECT_NOT_EXACT": evidence.affiliate_redirect_ready_count,
        "RUNTIME_REVALIDATION_NOT_EXACT": evidence.runtime_revalidation_ready_count,
    }
    for reason, count in exact_count_checks.items():
        if count != evidence.target_public_item_count:
            reasons.add(reason)

    boolean_checks = {
        "EXISTING_SURFACE_PRESERVATION_UNVERIFIED": evidence.existing_surface_preservation_verified,
        "SITEMAP_CAPACITY_UNVERIFIED": evidence.sitemap_capacity_verified,
        "SEO_QUALITY_UNREVIEWED": evidence.seo_quality_reviewed,
        "CLOUDFLARE_FREE_CAPACITY_UNVERIFIED": evidence.cloudflare_free_plan_capacity_verified,
        "COMPLIANCE_PUBLICATION_UNCONFIRMED": evidence.compliance_publication_confirmed,
        "PRODUCT_FUNNEL_WINDOW_NOT_CLOSED": evidence.product_funnel_window_closed,
        "ROLLBACK_PLAN_UNVERIFIED": evidence.rollback_plan_verified,
    }
    reasons.update(reason for reason, passed in boolean_checks.items() if passed is not True)

    actions = []
    if "CANDIDATE_SET_NOT_EXACT" in reasons or "ELIGIBILITY_NOT_EXACT" in reasons:
        actions.append("BUILD_ISOLATED_EXACT_300_ITEM_CANDIDATE")
    if any(
        reason in reasons for reason in (
            "IMAGE_COVERAGE_NOT_EXACT", "PRICE_COVERAGE_NOT_EXACT",
            "FRESHNESS_NOT_EXACT",
        )
    ):
        actions.append("VALIDATE_EXACT_300_ITEM_DATA_COVERAGE")
    if any(
        reason in reasons for reason in (
            "AFFILIATE_LOOKUP_NOT_EXACT", "AFFILIATE_REDIRECT_NOT_EXACT",
            "RUNTIME_REVALIDATION_NOT_EXACT",
        )
    ):
        actions.append("BUILD_EXACT_300_ITEM_D1_AND_RUNTIME_COVERAGE")
    if not evidence.existing_surface_preservation_verified or not evidence.rollback_plan_verified:
        actions.append("VERIFY_EXISTING_100_ITEM_SURFACE_AND_ROLLBACK")
    if not evidence.sitemap_capacity_verified or not evidence.seo_quality_reviewed:
        actions.append("REVIEW_CANONICAL_SITEMAP_AND_PAGE_QUALITY")
    if not evidence.cloudflare_free_plan_capacity_verified:
        actions.append("VERIFY_CLOUDFLARE_FREE_PLAN_CAPACITY")
    if not evidence.compliance_publication_confirmed or not evidence.product_funnel_window_closed:
        actions.append("OBTAIN_MANUAL_COMPLIANCE_AND_REVENUE_REVIEW")

    return _result(
        READY_FOR_MANUAL_EXPANSION_REVIEW if not reasons else BLOCKED,
        evidence.current_public_item_count,
        evidence.target_public_item_count,
        tuple(sorted(reasons)),
        tuple(dict.fromkeys(actions)),
    )


def current_evidence() -> ExpansionEvidence:
    verified_count = 0
    surface_preserved = False
    lookup_ready = 0
    redirect_ready = 0
    runtime_ready = 0
    sitemap_capacity = False
    rollback_verified = False
    seo_quality_reviewed = False
    try:
        value = json.loads(COLLECTION_EVIDENCE.read_text(encoding="utf-8"))
        evidence_valid = (
            type(value) is dict
            and value.get("version") == "0.1"
            and value.get("mode") == "COLLECTION_ONLY"
            and value.get("status") == "ISOLATED_COLLECTION_VERIFIED"
            and value.get("processed_items") == NEXT_STAGE_ITEM_COUNT
            and value.get("duplicate_content_ids") == 0
            and value.get("page_validation_status") == "PASS"
            and value.get("base_eligible_count") == NEXT_STAGE_ITEM_COUNT
            and value.get("fresh_base_eligible_count") == NEXT_STAGE_ITEM_COUNT
            and value.get("target_gap") == 0
            and value.get("collection_only_storage_committed") is True
            and value.get("source_identity_preserved") is True
            and value.get("production_database_write_performed") is False
            and value.get("publication_allowed") is False
            and value.get("sitemap_changed") is False
            and value.get("d1_changed") is False
            and value.get("production_schedule_changed") is False
            and type(value.get("retained_sha256")) is str
            and len(value["retained_sha256"]) == 64
            and all(character in "0123456789abcdef" for character in value["retained_sha256"])
        )
        if evidence_valid:
            verified_count = NEXT_STAGE_ITEM_COUNT
            surface_preserved = True
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass

    try:
        value = json.loads(SEO_QUALITY_EVIDENCE.read_text(encoding="utf-8"))
        seo_quality_reviewed = (
            type(value) is dict
            and value.get("version") == "0.1"
            and value.get("status") == "SEO_QUALITY_REVIEWED_KEEP_NOINDEX"
            and value.get("current_item_count") == CURRENT_PUBLIC_ITEM_COUNT
            and value.get("target_item_count") == NEXT_STAGE_ITEM_COUNT
            and value.get("complete_card_count") == CURRENT_PUBLIC_ITEM_COUNT
            and value.get("unique_cta_route_count") == CURRENT_PUBLIC_ITEM_COUNT
            and value.get("seo_quality_reviewed") is True
            and value.get("indexing_allowed") is False
            and value.get("detail_page_generation_allowed") is False
            and value.get("sitemap_change_allowed") is False
            and value.get("publication_allowed") is False
            and value.get("candidate_render_performance_verified") is False
            and type(value.get("source_sha256")) is dict
            and set(value["source_sha256"]) == {
                "sitemap.xml", "items/index.html", "items/item.html",
            }
            and all(
                type(digest) is str
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
                for digest in value["source_sha256"].values()
            )
            and value.get("reason_codes") == []
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass

    try:
        value = json.loads(ROLLBACK_EVIDENCE.read_text(encoding="utf-8"))
        rollback_verified = (
            type(value) is dict
            and value.get("version") == "0.1"
            and value.get("status") == "ROLLBACK_REHEARSAL_VERIFIED"
            and value.get("source_file_count") == 21
            and value.get("source_item_count") == CURRENT_PUBLIC_ITEM_COUNT
            and value.get("candidate_differed_from_source") is True
            and value.get("restore_byte_exact") is True
            and value.get("repeated_restore_deterministic") is True
            and value.get("source_unchanged") is True
            and value.get("rollback_plan_verified") is True
            and value.get("publication_allowed") is False
            and value.get("deployment_allowed") is False
            and value.get("external_io_performed") is False
            and type(value.get("source_snapshot_sha256")) is str
            and len(value["source_snapshot_sha256"]) == 64
            and all(
                character in "0123456789abcdef"
                for character in value["source_snapshot_sha256"]
            )
            and value.get("reason_codes") == []
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass

    try:
        value = json.loads(SITEMAP_CAPACITY_EVIDENCE.read_text(encoding="utf-8"))
        sitemap_capacity = (
            type(value) is dict
            and value.get("version") == "0.1"
            and value.get("status") == "SITEMAP_CAPACITY_VERIFIED"
            and value.get("target_item_count") == NEXT_STAGE_ITEM_COUNT
            and value.get("sitemap_capacity_verified") is True
            and value.get("seo_quality_reviewed") is False
            and value.get("publication_allowed") is False
            and value.get("sitemap_change_allowed") is False
            and value.get("target_additional_sitemap_urls") == 0
            and type(value.get("sitemap_url_count")) is int
            and 0 < value["sitemap_url_count"] <= 50_000
            and type(value.get("source_sha256")) is dict
            and set(value["source_sha256"]) == {
                "sitemap.xml", "robots.txt", "items/index.html", "items/item.html",
            }
            and all(
                type(digest) is str
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
                for digest in value["source_sha256"].values()
            )
            and value.get("reason_codes") == []
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass

    try:
        value = json.loads(D1_COVERAGE_EVIDENCE.read_text(encoding="utf-8"))
        d1_evidence_valid = (
            type(value) is dict
            and value.get("version") == "0.1"
            and value.get("status") == "INITIAL_BATCH_000_VERIFIED"
            and value.get("lookup_row_count") == 1287
            and value.get("candidate_lookup_ready_count") == 300
            and type(value.get("candidate_redirect_ready_count")) is int
            and 0 <= value["candidate_redirect_ready_count"] <= 300
            and type(value.get("candidate_runtime_revalidation_ready_count")) is int
            and 0 <= value["candidate_runtime_revalidation_ready_count"] <= 300
            and value.get("candidate_mapping_conflict_count") == 0
            and value.get("selected_count") == 5
            and value.get("valid_count") == 5
            and value.get("selected_rows_conditionally_approved") is True
            and value.get("selected_redirects_added") == 5
            and value.get("publication_allowed") is False
        )
        if d1_evidence_valid:
            lookup_ready = value["candidate_lookup_ready_count"]
            redirect_ready = value["candidate_redirect_ready_count"]
            runtime_ready = value["candidate_runtime_revalidation_ready_count"]
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        pass

    return ExpansionEvidence(
        current_public_item_count=CURRENT_PUBLIC_ITEM_COUNT,
        target_public_item_count=NEXT_STAGE_ITEM_COUNT,
        candidate_unique_item_count=verified_count,
        eligible_item_count=verified_count,
        image_ready_count=verified_count,
        price_ready_count=verified_count,
        fresh_item_count=verified_count,
        affiliate_lookup_ready_count=lookup_ready,
        affiliate_redirect_ready_count=redirect_ready,
        runtime_revalidation_ready_count=runtime_ready,
        existing_surface_preservation_verified=surface_preserved,
        sitemap_capacity_verified=sitemap_capacity,
        seo_quality_reviewed=seo_quality_reviewed,
        cloudflare_free_plan_capacity_verified=False,
        compliance_publication_confirmed=False,
        product_funnel_window_closed=False,
        rollback_plan_verified=rollback_verified,
    )


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {BLOCKED, READY_FOR_MANUAL_EXPANSION_REVIEW} else 2


if __name__ == "__main__":
    raise SystemExit(main())
