"""Build and verify an offline one-card CTA integration for the live item surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import hashlib
import re
from typing import Any

import revenue_mvp_minimal_opaque_go_cta_activation_freshness as freshness
import revenue_mvp_minimal_opaque_go_cta_activation_review as activation_review
import revenue_mvp_minimal_opaque_go_cta_contract as contract


VERSION = "0.1-candidate"
READY = "ONE_CARD_CTA_LIVE_INTEGRATION_CANDIDATE_READY"
PASS = "ONE_CARD_CTA_LIVE_INTEGRATION_PREFLIGHT_PASS"
BLOCKED = "ONE_CARD_CTA_LIVE_INTEGRATION_BLOCKED"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
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
        VERSION, BLOCKED, None, None, 0, 0, False, True,
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


def build_candidate(
    live_html: bytes, approved_artifact: bytes, *, evaluated_at: datetime
) -> tuple[bytes, LiveIntegrationReceipt]:
    """Insert the exact approved CTA into one matching card, in memory only."""
    try:
        if type(live_html) is not bytes or not live_html:
            raise LiveIntegrationFailure("LIVE_SOURCE_INVALID")
        source = live_html.decode("utf-8")
        if "affiliate-cta-block" in source or 'href="/go/' in source:
            raise LiveIntegrationFailure("LIVE_SOURCE_ALREADY_HAS_CTA")
        title, public_id = _approved_identity(approved_artifact, evaluated_at)
        marker = "<h2>" + escape(title) + "</h2>"
        if source.count(marker) != 1:
            raise LiveIntegrationFailure("MATCHING_CARD_NOT_UNIQUE")
        title_at = source.index(marker)
        article_start = source.rfind('<article class="item">', 0, title_at)
        article_end = source.find("</article>", title_at)
        if article_start < 0 or article_end < 0:
            raise LiveIntegrationFailure("MATCHING_CARD_STRUCTURE_INVALID")
        block = CTA_BLOCK.format(
            disclosure=escape(contract.DISCLOSURE), public_id=public_id
        )
        candidate = (
            source[:article_end] + block + source[article_end:]
        ).encode("utf-8")
        source_count = source.count('<article class="item">')
        result = LiveIntegrationReceipt(
            VERSION, READY, hashlib.sha256(live_html).hexdigest(),
            hashlib.sha256(candidate).hexdigest(), source_count, 1, True, True,
            reason_codes=(
                "EXACT_APPROVED_CTA_INSERTED_IN_ONE_MATCHING_CARD",
                "SOURCE_SURFACE_OTHERWISE_BYTE_PRESERVED",
                "SEPARATE_PREFLIGHT_AND_DEPLOYMENT_REQUIRED",
            ),
        )
        return candidate, result
    except (UnicodeDecodeError, ValueError) as error:
        if isinstance(error, LiveIntegrationFailure):
            raise
        raise LiveIntegrationFailure("LIVE_INTEGRATION_BUILD_FAILED") from error


def preflight(
    source: bytes, candidate: bytes, *, expected_candidate_sha256: Any,
    expected_item_count: Any,
) -> LiveIntegrationReceipt:
    """Prove the candidate differs from the source by one exact CTA block only."""
    try:
        if (
            type(expected_candidate_sha256) is not str
            or len(expected_candidate_sha256) != 64
            or hashlib.sha256(candidate).hexdigest() != expected_candidate_sha256
        ):
            return _blocked("CANDIDATE_DIGEST_MISMATCH")
        if type(expected_item_count) is not int or type(expected_item_count) is bool or expected_item_count < 1:
            return _blocked("ITEM_COUNT_INVALID")
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
