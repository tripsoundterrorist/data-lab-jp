"""Pure scope audit mapping doujin projection fields to reviewed rights policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import rights_decision_policy as rights


VERSION = "0.1"
READY = "READY_FOR_COMPLIANCE_SCOPE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"

DIRECT_MAPPINGS = {
    "title": "title",
    "current_price": "price",
    "makers": "maker",
    "series": "series",
    "genres": "genre",
    "image": "product_main_image",
    "source_product_url": "product_page_url",
}
DERIVED_MAPPINGS = {
    "discount_amount": "derived_price_comparison",
    "discount_rate": "derived_price_comparison",
}
INTERNAL_ONLY_FIELDS = ("projection_version", "source")
SCOPE_REVIEW_FIELDS = (
    "public_id", "release_date_raw", "list_price", "observed_at", "data_freshness"
)


@dataclass(frozen=True)
class DoujinRightsScopeAudit:
    version: str
    status: str
    direct_approved_fields: tuple[str, ...]
    derived_condition_fields: tuple[str, ...]
    internal_only_fields: tuple[str, ...]
    scope_review_required_fields: tuple[str, ...]
    source_policy_version: str
    field_rights_confirmed: bool
    publication_allowed: bool
    gate_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "direct_approved_fields", "derived_condition_fields",
            "internal_only_fields", "scope_review_required_fields", "reason_codes",
        ):
            value[key] = list(value[key])
        return value


def assess() -> DoujinRightsScopeAudit:
    try:
        if rights.validate_policy():
            raise ValueError("RIGHTS_POLICY_INVALID")
        for policy_field in (*DIRECT_MAPPINGS.values(), *DERIVED_MAPPINGS.values()):
            decision = rights.decision_for(policy_field)
            if (
                decision.public_display != rights.APPROVED
                or decision.evidence_type != rights.DIRECT_SUPPORT_CONFIRMATION
                or not decision.future_public_data_candidate
            ):
                raise ValueError("RIGHTS_MAPPING_NOT_APPROVED")
        return DoujinRightsScopeAudit(
            VERSION, READY, tuple(DIRECT_MAPPINGS), tuple(DERIVED_MAPPINGS),
            INTERNAL_ONLY_FIELDS, SCOPE_REVIEW_FIELDS, rights.POLICY_VERSION,
            False, False, False,
            (
                "EXISTING_RIGHTS_MAPPINGS_REUSED",
                "DOUJIN_SOURCE_SCOPE_REVIEW_REQUIRED",
                "UNMAPPED_FIELDS_REQUIRE_OFFICIAL_SCOPE_REVIEW",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return DoujinRightsScopeAudit(
            VERSION, FAIL_CLOSED, (), (), (), (), rights.POLICY_VERSION,
            False, False, False, ("DOUJIN_RIGHTS_SCOPE_AUDIT_ERROR",),
        )


if __name__ == "__main__":
    import json

    result = assess()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result.status == READY else 2)
