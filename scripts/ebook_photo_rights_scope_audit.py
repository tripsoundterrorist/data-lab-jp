"""Pure rights-scope audit for a future FANZA ebook photo projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import rights_decision_policy as rights


VERSION = "0.1"
READY = "READY_FOR_EBOOK_PHOTO_COMPLIANCE_SCOPE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"

REUSE_CANDIDATE_MAPPINGS = {
    "title": "title",
    "image": "product_main_image",
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
    "actresses",
    "authors",
    "manufactures",
)
PROHIBITED_FIELDS = ("product_description", "user_review_text", "raw_api_response")


@dataclass(frozen=True)
class EbookPhotoRightsScopeAudit:
    version: str
    status: str
    reuse_candidate_fields: tuple[str, ...]
    internal_only_fields: tuple[str, ...]
    scope_review_required_fields: tuple[str, ...]
    prohibited_fields: tuple[str, ...]
    source_policy_version: str
    exact_ebook_photo_scope_confirmed: bool
    contributor_semantics_confirmed: bool
    image_scope_confirmed: bool
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


def _failed(reason: str) -> EbookPhotoRightsScopeAudit:
    return EbookPhotoRightsScopeAudit(
        VERSION, FAIL_CLOSED, (), (), (), (), rights.POLICY_VERSION,
        False, False, False, False, False, False, (reason,),
    )


def assess() -> EbookPhotoRightsScopeAudit:
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
        for policy_field in PROHIBITED_FIELDS:
            if rights.decision_for(policy_field).public_display != rights.PROHIBITED:
                return _failed("PROHIBITED_FIELD_POLICY_DRIFT")
        return EbookPhotoRightsScopeAudit(
            VERSION,
            READY,
            tuple(REUSE_CANDIDATE_MAPPINGS),
            INTERNAL_ONLY_FIELDS,
            SCOPE_REVIEW_FIELDS,
            PROHIBITED_FIELDS,
            rights.POLICY_VERSION,
            False,
            False,
            False,
            False,
            False,
            False,
            (
                "EXISTING_RIGHTS_MAPPINGS_ARE_REVIEW_CANDIDATES_ONLY",
                "EXACT_EBOOK_PHOTO_SOURCE_SCOPE_REVIEW_REQUIRED",
                "FANZA_EBOOK_PHOTO_NOT_ASSUMED_EQUIVALENT_TO_DMM_PHOTO_BOOK",
                "ACTRESS_AUTHOR_AND_MANUFACTURE_SEMANTICS_UNCONFIRMED",
                "FANZA_EBOOK_PHOTO_IMAGE_SCOPE_REVIEW_REQUIRED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _failed("EBOOK_PHOTO_RIGHTS_SCOPE_AUDIT_ERROR")


if __name__ == "__main__":
    import json

    result = assess()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result.status == READY else 2)
