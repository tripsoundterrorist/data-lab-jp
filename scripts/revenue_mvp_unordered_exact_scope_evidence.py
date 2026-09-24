"""Validate the sanitized Compliance review for the exact unordered surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


VERSION = "0.1"
READY = "EXACT_UNORDERED_SCOPE_EVIDENCE_READY"
BLOCKED = "EXACT_UNORDERED_SCOPE_EVIDENCE_BLOCKED"
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT / "runtime/evidence/"
    "revenue-mvp-unordered-exact-scope-compliance-review-20260924.json"
)
ALLOWED_FIELDS = frozenset({
    "title", "api_observed_at", "transparency_notice", "current_price",
    "price_observed_at",
})
EXCLUDED_TOPICS = frozenset({
    "rank_order_offset_source_sort_or_review",
    "history_or_price_history",
    "availability_inventory_or_update_claim",
    "content_or_item_identifier",
    "url_or_affiliate_value",
    "affiliate_cta",
})


@dataclass(frozen=True)
class UnorderedExactScopeEvidence:
    version: str
    status: str
    exact_scope_verified: bool
    additional_lifecycle_sort_inquiry_required: bool
    expanded_scope_requires_new_review: bool
    publication_allowed: bool
    production_activation_allowed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_evidence() -> UnorderedExactScopeEvidence:
    try:
        value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        exact_keys = {
            "evidence_version", "reviewed_on", "base_main_commit",
            "scope_contract_version", "assessment", "presentation_mode",
            "allowed_fields", "excluded_topics",
            "expanded_scope_requires_new_review", "publication_allowed",
            "production_activation_allowed", "affiliate_eligibility_allowed",
            "gate_mutation_allowed",
        }
        valid = (
            type(value) is dict
            and set(value) == exact_keys
            and value["evidence_version"] == VERSION
            and value["reviewed_on"] == "2026-09-24"
            and value["base_main_commit"]
            == "ccf7f8970f4692c6cc805d6beed78ca71d0dc8ae"
            and value["scope_contract_version"] == "0.1"
            and value["assessment"]
            == "EXACT_SCOPE_NO_ADDITIONAL_INQUIRY_REQUIRED"
            and value["presentation_mode"] == "UNORDERED_GRID"
            and type(value["allowed_fields"]) is list
            and frozenset(value["allowed_fields"]) == ALLOWED_FIELDS
            and len(value["allowed_fields"]) == len(ALLOWED_FIELDS)
            and type(value["excluded_topics"]) is list
            and frozenset(value["excluded_topics"]) == EXCLUDED_TOPICS
            and len(value["excluded_topics"]) == len(EXCLUDED_TOPICS)
            and value["expanded_scope_requires_new_review"] is True
            and value["publication_allowed"] is False
            and value["production_activation_allowed"] is False
            and value["affiliate_eligibility_allowed"] is False
            and value["gate_mutation_allowed"] is False
        )
        if not valid:
            raise ValueError("exact scope evidence mismatch")
        return UnorderedExactScopeEvidence(
            VERSION, READY, True, False, True, False, False, False, False,
            (
                "EXACT_UNORDERED_SCOPE_REVIEWED",
                "EXPANDED_SCOPE_REQUIRES_NEW_REVIEW",
                "ALL_ACTIVATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return UnorderedExactScopeEvidence(
            VERSION, BLOCKED, False, True, True, False, False, False, False,
            ("EXACT_UNORDERED_SCOPE_EVIDENCE_INVALID",),
        )


def main() -> int:
    result = assess_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
