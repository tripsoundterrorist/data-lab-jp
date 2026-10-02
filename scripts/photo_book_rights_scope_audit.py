"""Pure rights-scope audit for a future DMM photo-book projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import rights_decision_policy as rights


VERSION = "0.1"
READY = "READY_FOR_PHOTO_BOOK_COMPLIANCE_SCOPE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"

REUSE_CANDIDATE_MAPPINGS = {
    "title": "title",
    "source_product_url": "product_page_url",
    "series": "series",
    "genres": "genre",
    "current_price": "price",
    "review_count": "review_count",
    "review_average": "review_average",
}
INTERNAL_ONLY_FIELDS = ("projection_version", "source")
SCOPE_REVIEW_FIELDS = (
    "public_id",
    "release_date_raw",
    "list_price",
    "observed_at",
    "data_freshness",
    "actors",
    "authors",
    "manufactures",
)
PROHIBITED_MAPPINGS = {
    "image": "dmm_books_product_image",
    "product_description": "product_description",
    "user_review_text": "user_review_text",
    "raw_api_response": "raw_api_response",
}


@dataclass(frozen=True)
class PhotoBookRightsScopeAudit:
    version: str
    status: str
    reuse_candidate_fields: tuple[str, ...]
    internal_only_fields: tuple[str, ...]
    scope_review_required_fields: tuple[str, ...]
    prohibited_fields: tuple[str, ...]
    source_policy_version: str
    exact_photo_book_scope_confirmed: bool
    contributor_semantics_confirmed: bool
    image_display_allowed: bool
    field_rights_confirmed: bool
    publication_allowed: bool
    gate_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "reuse_candidate_fields",
            "internal_only_fields",
            "scope_review_required_fields",
            "prohibited_fields",
            "reason_codes",
        ):
            result[key] = list(result[key])
        return result


def _failed(reason: str) -> PhotoBookRightsScopeAudit:
    return PhotoBookRightsScopeAudit(
        VERSION,
        FAIL_CLOSED,
        (),
        (),
        (),
        (),
        rights.POLICY_VERSION,
        False,
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def assess() -> PhotoBookRightsScopeAudit:
    try:
        if rights.validate_policy():
            return _failed("RIGHTS_POLICY_INVALID")
        for policy_field in REUSE_CANDIDATE_MAPPINGS.values():
            decision = rights.decision_for(policy_field)
            if (
                decision.public_display != rights.APPROVED
                or decision.evidence_type != rights.DIRECT_SUPPORT_CONFIRMATION
                or not decision.future_public_data_candidate
            ):
                return _failed("RIGHTS_REUSE_CANDIDATE_NOT_APPROVED")
        for policy_field in PROHIBITED_MAPPINGS.values():
            if rights.decision_for(policy_field).public_display != rights.PROHIBITED:
                return _failed("PROHIBITED_FIELD_POLICY_DRIFT")
        return PhotoBookRightsScopeAudit(
            VERSION,
            READY,
            tuple(REUSE_CANDIDATE_MAPPINGS),
            INTERNAL_ONLY_FIELDS,
            SCOPE_REVIEW_FIELDS,
            tuple(PROHIBITED_MAPPINGS),
            rights.POLICY_VERSION,
            False,
            False,
            False,
            False,
            False,
            False,
            (
                "EXISTING_RIGHTS_MAPPINGS_ARE_REVIEW_CANDIDATES_ONLY",
                "EXACT_PHOTO_BOOK_SOURCE_SCOPE_REVIEW_REQUIRED",
                "ACTOR_AUTHOR_AND_MANUFACTURE_SEMANTICS_UNCONFIRMED",
                "DMM_BOOKS_PRODUCT_IMAGE_REMAINS_PROHIBITED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _failed("PHOTO_BOOK_RIGHTS_SCOPE_AUDIT_ERROR")


if __name__ == "__main__":
    import json

    result = assess()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result.status == READY else 2)
