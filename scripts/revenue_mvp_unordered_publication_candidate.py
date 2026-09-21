"""Deterministic, offline candidate renderer for the approved reduced surface.

This module does not publish, deploy, mutate a Gate, or produce affiliate links.
Outputs are restricted to a caller-selected directory outside the repository.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import revenue_mvp_unordered_surface_review as contract


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2-candidate"
PACKET_VERSION = "0.1-candidate"
MAX_AGE = timedelta(hours=24)
TOP_LEVEL_FIELDS = frozenset({
    "version", "mode", "as_of", "transparency_notice", "candidates",
    "publication_allowed", "production_activation_allowed",
    "affiliate_eligibility_allowed", "gate_mutation_allowed", "cta_allowed",
})
ITEM_FIELDS = contract.ALLOWED_PUBLIC_FIELDS
ACTIVATION_FIELDS = (
    "publication_allowed", "production_activation_allowed",
    "affiliate_eligibility_allowed", "gate_mutation_allowed", "cta_allowed",
)


class CandidateFailure(ValueError):
    pass


@dataclass(frozen=True)
class CandidateReceipt:
    version: str
    status: str
    source_packet_sha256: str | None
    artifact_sha256: str | None
    candidate_count: int
    target_route: str | None
    output_written: bool
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    cta_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise CandidateFailure("TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise CandidateFailure("TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None:
        raise CandidateFailure("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def validate_packet(packet: Any, *, evaluated_at: datetime) -> list[dict[str, Any]]:
    if type(packet) is not dict or set(packet) != TOP_LEVEL_FIELDS:
        raise CandidateFailure("PACKET_SCHEMA_INVALID")
    if evaluated_at.tzinfo is None:
        raise CandidateFailure("EVALUATION_TIME_INVALID")
    if packet["version"] != PACKET_VERSION or packet["mode"] != contract.PRESENTATION_MODE:
        raise CandidateFailure("PACKET_CONTRACT_INVALID")
    if packet["transparency_notice"] != contract.TRANSPARENCY_NOTICE:
        raise CandidateFailure("TRANSPARENCY_NOTICE_INVALID")
    if any(packet.get(field) is not False for field in ACTIVATION_FIELDS):
        raise CandidateFailure("ACTIVATION_NOT_CLOSED")
    as_of = _timestamp(packet["as_of"])
    now = evaluated_at.astimezone(timezone.utc)
    if not timedelta(0) <= now - as_of <= MAX_AGE:
        raise CandidateFailure("PACKET_STALE")
    items = packet["candidates"]
    if type(items) is not list or not items:
        raise CandidateFailure("CANDIDATES_INVALID")
    validated: list[dict[str, Any]] = []
    for item in items:
        if type(item) is not dict or not contract.REQUIRED_PUBLIC_FIELDS <= set(item) <= ITEM_FIELDS:
            raise CandidateFailure("ITEM_SCHEMA_INVALID")
        if type(item["title"]) is not str or not item["title"].strip():
            raise CandidateFailure("TITLE_INVALID")
        if item["transparency_notice"] != contract.TRANSPARENCY_NOTICE:
            raise CandidateFailure("TRANSPARENCY_NOTICE_INVALID")
        observed = _timestamp(item["api_observed_at"])
        if observed > as_of or not timedelta(0) <= now - observed <= MAX_AGE:
            raise CandidateFailure("ITEM_STALE")
        price_fields = contract.PRICE_FIELDS & set(item)
        if price_fields and price_fields != contract.PRICE_FIELDS:
            raise CandidateFailure("PRICE_PROVENANCE_INCOMPLETE")
        if price_fields:
            if type(item["current_price"]) is not int or item["current_price"] < 0:
                raise CandidateFailure("PRICE_INVALID")
            if _timestamp(item["price_observed_at"]) != observed:
                raise CandidateFailure("PRICE_PROVENANCE_INVALID")
        validated.append(dict(item))
    return validated


def render(packet_bytes: bytes, *, evaluated_at: datetime, target_route: str) -> tuple[bytes, CandidateReceipt]:
    if type(target_route) is not str or not target_route.startswith("/") or "?" in target_route or "#" in target_route:
        raise CandidateFailure("TARGET_ROUTE_INVALID")
    try:
        packet = json.loads(packet_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateFailure("PACKET_JSON_INVALID") from error
    items = validate_packet(packet, evaluated_at=evaluated_at)
    cards = []
    for item in items:
        price = f'<p class="price">{item["current_price"]:,}円</p>' if "current_price" in item else ""
        cards.append(
            '<article class="item"><h2>' + escape(item["title"]) + '</h2>' + price
            + '<time>' + escape(item["api_observed_at"]) + '</time></article>'
        )
    html = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="canonical" href="https://datalabx.jp/items/"><link rel="stylesheet" href="items.css">'
        '<link rel="stylesheet" href="/analytics-consent.css"><script src="/analytics-consent.js" defer></script>'
        '<title>確認時点の商品情報 | DATA LAB</title></head><body><a class="skip-link" href="#main-content">本文へ移動</a>'
        '<header class="topbar"><h1>確認時点の商品情報</h1></header><main id="main-content">'
        '<p id="result-count" role="status" aria-live="polite">' + str(len(items)) + '件</p>'
        '<p id="page-status" aria-live="polite">1 / 1</p><section class="item-grid">'
        + ''.join(cards) + '</section><p class="notice">' + escape(contract.TRANSPARENCY_NOTICE)
        + '</p></main><footer class="site-footer"><nav aria-label="サイト情報">'
        '<a href="/about">DATA LABについて</a><a href="/disclosure">広告・データ表示方針</a>'
        '<a href="/privacy">プライバシー</a><a href="/terms">利用規約</a><a href="/contact">お問い合わせ</a>'
        '</nav></footer></body></html>\n'
    ).encode("utf-8")
    packet_hash = hashlib.sha256(packet_bytes).hexdigest()
    artifact_hash = hashlib.sha256(html).hexdigest()
    return html, CandidateReceipt(
        VERSION, "OFFLINE_CANDIDATE_READY", packet_hash, artifact_hash,
        len(items), target_route, False,
    )


def write_candidate(output: Path, payload: bytes) -> None:
    target = output.resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise CandidateFailure("OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="publication-candidate-", suffix=".tmp", dir=target.parent)
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


__all__ = ["CandidateFailure", "CandidateReceipt", "MAX_AGE", "render", "validate_packet", "write_candidate"]
