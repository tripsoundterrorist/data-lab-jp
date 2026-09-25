"""Render one isolated, review-only HTML artifact from a minimal CTA packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

import revenue_mvp_minimal_opaque_go_cta_contract as cta_contract
import revenue_mvp_minimal_opaque_go_cta_packet as packet_contract
import revenue_mvp_unordered_surface_review as unordered_contract


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1-candidate"
READY = "MINIMAL_OPAQUE_GO_CTA_ARTIFACT_READY"
MAX_AGE = timedelta(hours=24)
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SELECTION_METHOD = "OPAQUE_ID_LEXICOGRAPHIC_MIN_NO_RANKING_MEANING"
TOP_LEVEL_FIELDS = frozenset({
    "version", "source_packet_sha256", "as_of", "selection_method",
    "source_candidate_count", "candidates", "publication_allowed",
    "production_activation_allowed", "affiliate_eligibility_allowed",
    "gate_mutation_allowed", "deployment_allowed",
})
ACTIVATION_FIELDS = (
    "publication_allowed", "production_activation_allowed",
    "affiliate_eligibility_allowed", "gate_mutation_allowed", "deployment_allowed",
)
CTA_FIELDS = frozenset({
    "public_id", "cta_href", "disclosure_text", "disclosure_proximate",
})


class CtaRendererFailure(ValueError):
    pass


@dataclass(frozen=True)
class CtaArtifactReceipt:
    version: str
    status: str
    source_packet_sha256: str
    artifact_sha256: str
    candidate_count: int
    cta_count: int
    target_route: str
    output_written: bool
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    deployment_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise CtaRendererFailure("TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as error:
        raise CtaRendererFailure("TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None:
        raise CtaRendererFailure("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def validate(packet: Any, *, evaluated_at: datetime) -> dict[str, Any]:
    if type(packet) is not dict or set(packet) != TOP_LEVEL_FIELDS:
        raise CtaRendererFailure("PACKET_SCHEMA_INVALID")
    if evaluated_at.tzinfo is None:
        raise CtaRendererFailure("EVALUATION_TIME_INVALID")
    if packet["version"] != packet_contract.VERSION:
        raise CtaRendererFailure("PACKET_VERSION_INVALID")
    if type(packet["source_packet_sha256"]) is not str or SHA256.fullmatch(
        packet["source_packet_sha256"]
    ) is None:
        raise CtaRendererFailure("SOURCE_PACKET_DIGEST_INVALID")
    if packet["selection_method"] != SELECTION_METHOD:
        raise CtaRendererFailure("SELECTION_METHOD_INVALID")
    if type(packet["source_candidate_count"]) is not int or packet[
        "source_candidate_count"
    ] < 1:
        raise CtaRendererFailure("SOURCE_COUNT_INVALID")
    if any(packet[field] is not False for field in ACTIVATION_FIELDS):
        raise CtaRendererFailure("ACTIVATION_NOT_CLOSED")
    now = evaluated_at.astimezone(timezone.utc)
    as_of = _timestamp(packet["as_of"])
    if not timedelta(0) <= now - as_of <= MAX_AGE:
        raise CtaRendererFailure("PACKET_STALE")
    candidates = packet["candidates"]
    if type(candidates) is not list or len(candidates) != 1:
        raise CtaRendererFailure("EXACTLY_ONE_CANDIDATE_REQUIRED")
    candidate = candidates[0]
    allowed = unordered_contract.ALLOWED_PUBLIC_FIELDS | CTA_FIELDS
    required = unordered_contract.REQUIRED_PUBLIC_FIELDS | CTA_FIELDS
    if type(candidate) is not dict or not required <= set(candidate) <= allowed:
        raise CtaRendererFailure("CANDIDATE_SCHEMA_INVALID")
    if type(candidate["title"]) is not str or not candidate["title"].strip():
        raise CtaRendererFailure("TITLE_INVALID")
    if candidate["transparency_notice"] != unordered_contract.TRANSPARENCY_NOTICE:
        raise CtaRendererFailure("TRANSPARENCY_NOTICE_INVALID")
    observed = _timestamp(candidate["api_observed_at"])
    if observed > as_of or not timedelta(0) <= now - observed <= MAX_AGE:
        raise CtaRendererFailure("CANDIDATE_STALE")
    price_fields = unordered_contract.PRICE_FIELDS & set(candidate)
    if price_fields and price_fields != unordered_contract.PRICE_FIELDS:
        raise CtaRendererFailure("PRICE_PROVENANCE_INCOMPLETE")
    if price_fields and (
        type(candidate["current_price"]) is not int
        or candidate["current_price"] < 0
        or _timestamp(candidate["price_observed_at"]) != observed
    ):
        raise CtaRendererFailure("PRICE_INVALID")
    review = cta_contract.review({
        "contract_version": cta_contract.VERSION,
        "public_id": candidate["public_id"],
        "cta_href": candidate["cta_href"],
        "disclosure_text": candidate["disclosure_text"],
        "disclosure_proximate": candidate["disclosure_proximate"],
        "affiliate_url_exposed": False,
        "server_side_lookup_required": True,
        "rate_limit_required": True,
        "publication_scope_expanded": True,
        "exact_unordered_scope_unchanged": True,
    })
    if not review.eligible_for_implementation_review:
        raise CtaRendererFailure("CTA_CONTRACT_BLOCKED")
    return dict(candidate)


def render(
    packet_bytes: bytes, *, evaluated_at: datetime, target_route: str = "/items/"
) -> tuple[bytes, CtaArtifactReceipt]:
    if target_route != "/items/":
        raise CtaRendererFailure("TARGET_ROUTE_INVALID")
    try:
        packet = json.loads(packet_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CtaRendererFailure("PACKET_JSON_INVALID") from error
    candidate = validate(packet, evaluated_at=evaluated_at)
    price = ""
    if "current_price" in candidate:
        price = f'<p class="price">{candidate["current_price"]:,}円</p>'
    html = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,nofollow">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="canonical" href="https://datalabx.jp/items/">'
        '<link rel="stylesheet" href="items.css">'
        '<title>公開前CTA確認 | DATA LAB</title></head><body>'
        '<main id="main-content"><p class="review-only">公開前・確認専用</p>'
        '<article class="item"><h1>' + escape(candidate["title"]) + '</h1>'
        + price + '<time datetime="' + escape(candidate["api_observed_at"]) + '">'
        + escape(candidate["api_observed_at"]) + '</time>'
        '<aside class="affiliate-cta-block" aria-label="広告リンク">'
        '<p class="affiliate-cta-disclosure">' + escape(candidate["disclosure_text"]) + '</p>'
        '<a class="affiliate-cta-link" href="' + escape(candidate["cta_href"], quote=True)
        + '" target="_blank" rel="noopener noreferrer sponsored">FANZAの商品ページを確認（外部サイト）</a>'
        '</aside></article><p class="notice">'
        + escape(candidate["transparency_notice"]) + '</p></main></body></html>\n'
    ).encode("utf-8")
    source_hash = hashlib.sha256(packet_bytes).hexdigest()
    artifact_hash = hashlib.sha256(html).hexdigest()
    receipt = CtaArtifactReceipt(
        VERSION, READY, source_hash, artifact_hash, 1, 1, target_route, False,
    )
    return html, receipt


def write_candidate(output: Path, payload: bytes) -> None:
    target = output.resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise CtaRendererFailure("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="minimal-cta-candidate-", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


__all__ = [
    "CtaArtifactReceipt", "CtaRendererFailure", "READY", "VERSION",
    "render", "validate", "write_candidate",
]
