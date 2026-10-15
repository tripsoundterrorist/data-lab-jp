"""Offline raw-response comparison only; not a trusted public capture adapter.

Caller-supplied HTTP metadata cannot establish provenance. A match never creates
_PageObservation, grants publication, or proves current product eligibility.
No browser control, networking, credentials, file I/O or persistence occurs here.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256

import revenue_mvp_price_display_transition as transition
import revenue_mvp_price_filter_copy_candidate as copy_candidate


@dataclass(frozen=True)
class RawHtmlReview:
    status: str
    reason_code: str
    artifact_sha256: str | None = None
    supplied_response_match: bool = False
    trusted_public_capture: bool = False
    current_eligibility_verified: bool = False
    publication_allowed: bool = False
    gate_mutation_allowed: bool = False


def review(*, body, expected_sha256, requested_url, final_url, http_status,
           content_type, content_encoding, source_kind, observed_at, evaluated_at):
    """Compare supplied, decoded response bytes; never accept DOM serialization.

Content-Encoding must be absent or identity: compressed wire bytes need a
separate bounded decoding adapter. Charset must be absent or UTF-8. Timestamps
are caller claims and are freshness checks only, not authenticated provenance.
"""
    def blocked(reason):
        return RawHtmlReview("BLOCKED", reason)

    if expected_sha256 not in (transition.CANDIDATE, copy_candidate.CANDIDATE_SHA256):
        return blocked("EXPECTED_ARTIFACT_NOT_ALLOWLISTED")
    if source_kind != "http_response_body":
        return blocked("RAW_HTTP_RESPONSE_REQUIRED")
    if requested_url != transition.URL or final_url != transition.URL:
        return blocked("EXACT_ORIGIN_AND_PATH_REQUIRED")
    if type(http_status) is not int or http_status != 200:
        return blocked("HTTP_SUCCESS_REQUIRED")
    if type(content_type) is not str or type(content_encoding) is not str:
        return blocked("RESPONSE_METADATA_INVALID")
    media = [part.strip().lower() for part in content_type.split(";")]
    if (media[0] != "text/html" or
            any(part not in ('charset=utf-8', 'charset="utf-8"') for part in media[1:]) or
            len(media) > 2 or content_encoding.strip().lower() not in ("", "identity")):
        return blocked("HTML_UTF8_IDENTITY_REQUIRED")
    if type(body) is not bytes or not body or len(body) > transition.MAX_BYTES:
        return blocked("BODY_SIZE_OR_TYPE_INVALID")
    try:
        if (not isinstance(observed_at, datetime) or not isinstance(evaluated_at, datetime)
                or observed_at.tzinfo is None or evaluated_at.tzinfo is None
                or not timedelta(0) <= evaluated_at - observed_at <= timedelta(minutes=15)):
            return blocked("RESPONSE_TIME_INVALID")
        digest = sha256(transition.canonical(body)).hexdigest()
    except (ValueError, TypeError, UnicodeError, OverflowError):
        return blocked("RESPONSE_INPUT_INVALID")
    if digest != expected_sha256:
        return blocked("EXACT_ARTIFACT_MISMATCH")
    return RawHtmlReview("SUPPLIED_RESPONSE_MATCH_NOT_TRUSTED_CAPTURE",
                         "PROVENANCE_ADAPTER_AND_SEPARATE_REVIEW_REQUIRED", digest, True)
