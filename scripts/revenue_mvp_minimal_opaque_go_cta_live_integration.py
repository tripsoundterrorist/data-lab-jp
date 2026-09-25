"""Build and verify an offline one-card CTA integration for the live item surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape, unescape
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import revenue_mvp_minimal_opaque_go_cta_activation_freshness as freshness
import revenue_mvp_minimal_opaque_go_cta_activation_review as activation_review
import revenue_mvp_minimal_opaque_go_cta_contract as contract
from revenue_mvp_lifecycle_receipt import public_item_id
import revenue_mvp_unordered_review_packet as unordered


VERSION = "0.1-candidate"
READY = "ONE_CARD_CTA_LIVE_INTEGRATION_CANDIDATE_READY"
PASS = "ONE_CARD_CTA_LIVE_INTEGRATION_PREFLIGHT_PASS"
BLOCKED = "ONE_CARD_CTA_LIVE_INTEGRATION_BLOCKED"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
SOURCE_SHA256 = "564bbeaf628de624e816ff8f2b4a3824119e338d3052e8d2594a084f06ef2e85"
APPROVED_ARTIFACT_SHA256 = "f273ec05089eabd19da50e7d62dfb2f747282f53d37f9babcb7a63c79c78dcf9"
APPROVAL_EVIDENCE_PATH = (Path(__file__).resolve().parents[1] / "docs/evidence/revenue-mvp-minimal-opaque-go-cta-user-approval-20260925.json")
ITEM_COUNT = 100
CARD = re.compile(r'<article class="item"><h2>(.*?)</h2><p class="price">([0-9][0-9,]*)円</p><time>([^<]+)</time></article>', re.DOTALL)
CTA_BLOCK = (
    '<aside class="affiliate-cta-block" aria-label="広告リンク">'
    '<p class="affiliate-cta-disclosure">{disclosure}</p>'
    '<a class="affiliate-cta-link" href="/go/{public_id}" target="_blank" '
    'rel="noopener noreferrer sponsored">FANZAの商品ページを確認（外部サイト）</a>'
    '</aside>'
)


class LiveIntegrationFailure(ValueError):
    pass


@dataclass(frozen=True)
class LiveIntegrationReceipt:
    version: str
    status: str
    source_sha256: str | None
    candidate_sha256: str | None
    item_count: int
    cta_count: int
    source_preserved_except_exact_cta: bool
    explicit_activation_approval_recorded: bool
    output_written: bool = False
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    d1_write_allowed: bool = False
    deployment_allowed: bool = False
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> LiveIntegrationReceipt:
    return LiveIntegrationReceipt(
        VERSION, BLOCKED, None, None, 0, 0, False, False,
        reason_codes=(reason,),
    )


class _ApprovedArtifactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_h1 = False
        self.title_parts: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "h1":
            self.in_h1 = True
        if tag == "a" and "affiliate-cta-link" in set((values.get("class") or "").split()):
            self.hrefs.append(values.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self.in_h1 = False

    def handle_data(self, data: str) -> None:
        if self.in_h1:
            self.title_parts.append(data)


def _approved_identity(artifact: bytes, evaluated_at: datetime) -> tuple[str, str]:
    if type(artifact) is not bytes or hashlib.sha256(artifact).hexdigest() != APPROVED_ARTIFACT_SHA256:
        raise LiveIntegrationFailure("APPROVED_ARTIFACT_DIGEST_MISMATCH")
    if activation_review.COMPLIANCE_APPROVED_ARTIFACT_SHA256 != APPROVED_ARTIFACT_SHA256:
        raise LiveIntegrationFailure("APPROVED_ARTIFACT_DIGEST_MISMATCH")
    result = freshness.review(artifact, evaluated_at=evaluated_at)
    if result.status != freshness.FRESH or not result.freshness_confirmed:
        raise LiveIntegrationFailure("APPROVED_ARTIFACT_NOT_FRESH")
    parser = _ApprovedArtifactParser()
    parser.feed(artifact.decode("utf-8"))
    parser.close()
    if len(parser.hrefs) != 1 or not parser.title_parts:
        raise LiveIntegrationFailure("APPROVED_ARTIFACT_IDENTITY_INVALID")
    href = parser.hrefs[0]
    if not href.startswith("/go/") or PUBLIC_ID.fullmatch(href[4:]) is None:
        raise LiveIntegrationFailure("APPROVED_ARTIFACT_IDENTITY_INVALID")
    return "".join(parser.title_parts), href[4:]


def _approval_scope_valid() -> None:
    try:
        value = json.loads(APPROVAL_EVIDENCE_PATH.read_text(encoding="utf-8"))
        if type(value) is not dict or value.get("version") != "0.1" or value.get("source") != "CONTROL_CENTER_USER_MESSAGE" or value.get("decision") != "APPROVED":
            raise ValueError
        scope = value.get("approved_scope")
        if type(scope) is not dict or any((
            type(scope.get("artifact_sha256")) is not str or scope["artifact_sha256"] != APPROVED_ARTIFACT_SHA256,
            type(scope.get("public_route")) is not str or scope["public_route"] != "/items/",
            type(scope.get("cta_route_prefix")) is not str or scope["cta_route_prefix"] != "/go/",
            type(scope.get("maximum_cta_count")) is not int or scope["maximum_cta_count"] != 1,
            type(scope.get("existing_live_item_count_must_be_preserved")) is not int or scope["existing_live_item_count_must_be_preserved"] != ITEM_COUNT,
            any(scope.get(name) is not True for name in ("opaque_public_id_only", "proximate_pr_disclosure_required", "free_plan_only")),
        )):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise LiveIntegrationFailure("APPROVAL_SCOPE_INVALID") from None


def _source_cards(source: str) -> list[tuple[str, int, str, int]]:
    cards = []
    for match in CARD.finditer(source):
        price_text = match.group(2)
        price = int(price_text.replace(",", ""))
        if f"{price:,}" != price_text:
            raise LiveIntegrationFailure("LIVE_CARD_PRICE_INVALID")
        cards.append((unescape(match.group(1)), price, match.group(3), match.end() - len("</article>")))
    if len(cards) != ITEM_COUNT or source.count('<article class="item">') != ITEM_COUNT:
        raise LiveIntegrationFailure("SOURCE_ITEM_COUNT_MISMATCH")
    return cards


def _database_identity(database: Path, card: tuple[str, int, str, int], approved_public_id: str) -> bool:
    connection = None
    try:
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute("""
            SELECT i.site, i.service, i.floor, i.content_id, s.observed_at
            FROM item_snapshots AS s
            JOIN items AS i ON i.id = s.item_id
            JOIN item_snapshot_titles AS t ON t.snapshot_id = s.id
            WHERE t.title = ? AND s.price_min = ? AND t.observed_at = s.observed_at
        """, (card[0], card[1])).fetchall()
        matches = [row for row in rows if unordered.iso_utc(unordered.parse_timestamp(row[4])) == card[2]]
        if len(matches) != 1:
            raise LiveIntegrationFailure("DATABASE_CARD_BINDING_NOT_UNIQUE")
        identity = matches[0][:4]
        if not all(type(part) is str and part for part in identity):
            raise LiveIntegrationFailure("DATABASE_IDENTITY_INVALID")
        return public_item_id(*identity) == approved_public_id
    except LiveIntegrationFailure:
        raise
    except (sqlite3.Error, ValueError, TypeError):
        raise LiveIntegrationFailure("DATABASE_CARD_BINDING_INVALID") from None
    finally:
        if connection is not None:
            connection.close()


def _database_digest(database: Path) -> str:
    if not database.is_file() or any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise LiveIntegrationFailure("DATABASE_READ_ONLY_STATE_INVALID")
    try:
        return unordered.file_sha256(database)
    except OSError:
        raise LiveIntegrationFailure("DATABASE_READ_FAILED") from None


def build_candidate(
    live_html: bytes, approved_artifact: bytes, *, database: Path, evaluated_at: datetime
) -> tuple[bytes, LiveIntegrationReceipt]:
    """Insert the exact approved CTA into one matching card, in memory only."""
    try:
        if type(live_html) is not bytes or hashlib.sha256(live_html).hexdigest() != SOURCE_SHA256:
            raise LiveIntegrationFailure("LIVE_SOURCE_INVALID")
        if not isinstance(database, Path):
            raise LiveIntegrationFailure("DATABASE_PATH_INVALID")
        _approval_scope_valid()
        database = database.resolve(strict=True)
        database_before = _database_digest(database)
        source = live_html.decode("utf-8")
        if "affiliate-cta-block" in source or 'href="/go/' in source:
            raise LiveIntegrationFailure("LIVE_SOURCE_ALREADY_HAS_CTA")
        title, public_id = _approved_identity(approved_artifact, evaluated_at)
        cards = _source_cards(source)
        bound = [card for card in cards if card[0] == title and _database_identity(database, card, public_id)]
        if len(bound) != 1:
            raise LiveIntegrationFailure("APPROVED_PUBLIC_ID_CARD_BINDING_NOT_UNIQUE")
        article_end = bound[0][3]
        block = CTA_BLOCK.format(
            disclosure=escape(contract.DISCLOSURE), public_id=public_id
        )
        candidate = (
            source[:article_end] + block + source[article_end:]
        ).encode("utf-8")
        if _database_digest(database) != database_before:
            raise LiveIntegrationFailure("DATABASE_CHANGED_DURING_BINDING")
        result = LiveIntegrationReceipt(
            VERSION, READY, hashlib.sha256(live_html).hexdigest(),
            hashlib.sha256(candidate).hexdigest(), ITEM_COUNT, 1, True, True,
            reason_codes=(
                "EXACT_APPROVED_CTA_INSERTED_IN_ONE_MATCHING_CARD",
                "SOURCE_SURFACE_OTHERWISE_BYTE_PRESERVED",
                "SEPARATE_PREFLIGHT_AND_DEPLOYMENT_REQUIRED",
            ),
        )
        return candidate, result
    except (UnicodeDecodeError, ValueError, OSError) as error:
        if isinstance(error, LiveIntegrationFailure):
            raise
        raise LiveIntegrationFailure("LIVE_INTEGRATION_BUILD_FAILED") from None


def preflight(
    source: bytes, candidate: bytes, *, expected_candidate_sha256: Any,
    expected_item_count: Any, approved_artifact: bytes, database: Path,
    evaluated_at: datetime,
) -> LiveIntegrationReceipt:
    """Prove the candidate differs from the source by one exact CTA block only."""
    try:
        if (
            type(expected_candidate_sha256) is not str
            or len(expected_candidate_sha256) != 64
            or hashlib.sha256(candidate).hexdigest() != expected_candidate_sha256
        ):
            return _blocked("CANDIDATE_DIGEST_MISMATCH")
        if type(source) is not bytes or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
            return _blocked("LIVE_SOURCE_INVALID")
        if type(expected_item_count) is not int or expected_item_count != ITEM_COUNT:
            return _blocked("ITEM_COUNT_INVALID")
        rebuilt, build_receipt = build_candidate(
            source, approved_artifact, database=database, evaluated_at=evaluated_at,
        )
        if build_receipt.status != READY or rebuilt != candidate:
            return _blocked("APPROVED_DB_BOUND_CANDIDATE_REQUIRED")
        source_text = source.decode("utf-8")
        candidate_text = candidate.decode("utf-8")
        if source_text.count('<article class="item">') != expected_item_count:
            return _blocked("SOURCE_ITEM_COUNT_MISMATCH")
        if candidate_text.count('<article class="item">') != expected_item_count:
            return _blocked("CANDIDATE_ITEM_COUNT_MISMATCH")
        matches = re.findall(
            r'<aside class="affiliate-cta-block" aria-label="広告リンク">'
            r'<p class="affiliate-cta-disclosure">【PR】FANZAで確認</p>'
            r'<a class="affiliate-cta-link" href="/go/(itm_[0-9a-f]{24})" target="_blank" '
            r'rel="noopener noreferrer sponsored">FANZAの商品ページを確認（外部サイト）</a>'
            r'</aside>', candidate_text,
        )
        if len(matches) != 1:
            return _blocked("EXACT_CTA_BLOCK_REQUIRED")
        block = CTA_BLOCK.format(disclosure=contract.DISCLOSURE, public_id=matches[0])
        if candidate_text.replace(block, "", 1) != source_text:
            return _blocked("SOURCE_NOT_BYTE_PRESERVED")
        if candidate_text.count('href="/go/') != 1:
            return _blocked("EXACT_ONE_GO_LINK_REQUIRED")
        return LiveIntegrationReceipt(
            VERSION, PASS, hashlib.sha256(source).hexdigest(),
            expected_candidate_sha256, expected_item_count, 1, True, True,
            reason_codes=(
                "ONE_CARD_CTA_DIFF_EXACTLY_VERIFIED",
                "EXPLICIT_PRODUCTION_EXECUTION_STILL_REQUIRED",
            ),
        )
    except (UnicodeDecodeError, ValueError):
        return _blocked("LIVE_INTEGRATION_PREFLIGHT_FAILED")
    except Exception:
        return _blocked("LIVE_INTEGRATION_PREFLIGHT_ERROR")


__all__ = [
    "BLOCKED", "LiveIntegrationFailure", "LiveIntegrationReceipt", "PASS", "READY",
    "VERSION", "build_candidate", "preflight",
]
