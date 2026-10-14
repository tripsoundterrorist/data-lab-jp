"""Separate price-display observation receipt; never a publication/eligibility Gate.

Historical evidence is checked against the unchanged baseline, never rewritten.
Only this module's fixed-origin read-only capture can supply a live observation.
Capture is not invoked by default, and no CLI/scheduler integration is provided.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Mapping
import urllib.request

BASELINE = "21cebab8b202129658fe192055cd72b6cf3cd197765a18cc5b92378104457db1"
CANDIDATE = "07083ce28e1095ce75ea89fa453ecb8c3e6fc6626e679397ca046d167d59d88b"
URL = "https://datalabx.jp/items/"
_TOKEN = object()
MAX_BYTES = 1024 * 1024


def canonical(data):
    if type(data) is not bytes:
        raise ValueError
    return data.decode("utf-8").replace("\r\n","\n").replace("\r","\n").encode("utf-8")


@dataclass(frozen=True)
class _PageObservation:
    digest: str
    observed_at: datetime
    _token: object = field(repr=False)


@dataclass(frozen=True)
class TransitionReceipt:
    status: str
    reason_code: str
    baseline_sha256: str | None = None
    candidate_sha256: str | None = None
    historical_binding_valid: bool = False
    current_display_match_observed: bool = False
    publication_allowed: bool = False
    gate_mutation_allowed: bool = False
    database_write_performed: bool = False


def capture_public_page():
    """Explicit read-only HTTP capture. No cookies, credentials or persistence."""
    request = urllib.request.Request(URL, headers={"Accept":"text/html"}, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        if (type(response.status) is not int or response.status != 200
                or response.geturl() != URL):
            raise ValueError("PUBLIC_PAGE_CAPTURE_INVALID")
        body = response.read(MAX_BYTES + 1)
        if type(body) is not bytes or len(body) > MAX_BYTES:
            raise ValueError("PUBLIC_PAGE_CAPTURE_INVALID")
    return _PageObservation(sha256(canonical(body)).hexdigest(),
                            datetime.now(timezone.utc), _TOKEN)


def review(baseline: bytes, candidate: bytes, historical_evidence: Mapping,
           *, observation=None, evaluated_at=None):
    def blocked(reason):
        return TransitionReceipt("BLOCKED", reason)
    try:
        old, new = canonical(baseline), canonical(candidate)
        old_digest, new_digest = sha256(old).hexdigest(), sha256(new).hexdigest()
        if old_digest != BASELINE or new_digest != CANDIDATE:
            return blocked("EXACT_DISPLAY_DELTA_BINDING_INVALID")
        if (new.count('円〜</p>'.encode()) != 100
                or new.replace('円〜</p>'.encode(),'円</p>'.encode()) != old):
            return blocked("NON_PRICE_DISPLAY_CHANGE")
        if (not isinstance(historical_evidence,Mapping)
                or historical_evidence.get("items_artifact_sha256") != old_digest):
            return blocked("HISTORICAL_BASELINE_BINDING_INVALID")
        # This is only a binding check, not renewed historical live verification.
        if observation is None:
            return TransitionReceipt("CANDIDATE_PENDING_LIVE_DISPLAY_VERIFICATION",
                "HISTORICAL_EVIDENCE_RETAINED_NOT_REUSED_FOR_CANDIDATE",
                old_digest,new_digest,True)
        if type(observation) is not _PageObservation or observation._token is not _TOKEN:
            return blocked("TRUSTED_PUBLIC_CAPTURE_REQUIRED")
        now = evaluated_at or datetime.now(timezone.utc)
        if (not isinstance(now,datetime) or now.tzinfo is None
                or observation.observed_at.tzinfo is None
                or not timedelta(0) <= now - observation.observed_at <= timedelta(minutes=15)):
            return blocked("PUBLIC_CAPTURE_STALE_OR_FUTURE")
        if observation.digest == old_digest:
            return TransitionReceipt("CANDIDATE_NOT_YET_PUBLIC",
                "PUBLIC_PAGE_STILL_MATCHES_HISTORICAL_BASELINE",
                old_digest,new_digest,True)
        if observation.digest != new_digest:
            return blocked("PUBLIC_DISPLAY_MISMATCH")
        return TransitionReceipt("LIVE_DISPLAY_MATCH_OBSERVED",
            "DISPLAY_ONLY_NOT_ELIGIBILITY_OR_PUBLICATION_AUTHORITY",
            old_digest,new_digest,True,True)
    except (ValueError,TypeError,AttributeError,UnicodeError,OverflowError):
        return blocked("TRANSITION_INPUT_INVALID")
