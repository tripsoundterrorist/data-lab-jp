"""Fail-closed structural preflight for one offline minimal CTA artifact."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from html.parser import HTMLParser
import re
from typing import Any

import revenue_mvp_minimal_opaque_go_cta_contract as contract


VERSION = "0.1-candidate"
PASS = "MINIMAL_OPAQUE_GO_CTA_ARTIFACT_PREFLIGHT_PASS"
BLOCKED = "MINIMAL_OPAQUE_GO_CTA_ARTIFACT_PREFLIGHT_BLOCKED"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HREF = re.compile(r"/go/(itm_[0-9a-f]{24})\Z")
FORBIDDEN = (
    "affiliateURL", "DMM_API_ID", "DMM_AFFILIATE_ID", "api_id=",
    "affiliate_id=", "https://al.dmm", "https://al.fanza",
)


@dataclass(frozen=True)
class ArtifactPreflightResult:
    version: str
    status: str
    artifact_sha256: str | None
    cta_count: int
    disclosure_count: int
    noindex_confirmed: bool
    same_origin_confirmed: bool
    proximate_disclosure_confirmed: bool
    eligible_for_manual_activation_review: bool
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    deployment_allowed: bool = False
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str, digest: str | None = None) -> ArtifactPreflightResult:
    return ArtifactPreflightResult(
        VERSION, BLOCKED, digest, 0, 0, False, False, False, False,
        reason_codes=(reason,),
    )


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.noindex = 0
        self.ctas: list[tuple[str, str, str]] = []
        self.disclosures: list[str] = []
        self.sequence: list[str] = []
        self.depth = 0
        self.in_cta_block = False
        self.capture: str | None = None
        self.buffer: list[str] = []
        self.forbidden_element = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"script", "iframe", "form", "img", "video", "audio"}:
            self.forbidden_element = True
        if tag == "meta" and values.get("name") == "robots" and values.get("content") == "noindex,nofollow":
            self.noindex += 1
        classes = set((values.get("class") or "").split())
        if tag == "aside" and "affiliate-cta-block" in classes:
            if self.in_cta_block:
                self.forbidden_element = True
            self.in_cta_block = True
            self.depth = 1
            self.sequence = []
            return
        if self.in_cta_block:
            self.depth += 1
            if tag == "p" and "affiliate-cta-disclosure" in classes:
                self.capture, self.buffer = "disclosure", []
                self.sequence.append("disclosure")
            elif tag == "a" and "affiliate-cta-link" in classes:
                self.ctas.append((values.get("href") or "", values.get("rel") or "", values.get("target") or ""))
                self.sequence.append("cta")
            else:
                self.sequence.append("other")

    def handle_endtag(self, tag: str) -> None:
        if self.in_cta_block and self.capture == "disclosure" and tag == "p":
            self.disclosures.append("".join(self.buffer).strip())
            self.capture, self.buffer = None, []
        if self.in_cta_block:
            self.depth -= 1
            if self.depth == 0:
                self.in_cta_block = False

    def handle_data(self, data: str) -> None:
        if self.capture == "disclosure":
            self.buffer.append(data)


def review(artifact: bytes, expected_sha256: Any) -> ArtifactPreflightResult:
    try:
        if type(artifact) is not bytes or not artifact:
            return _blocked("ARTIFACT_INVALID")
        if type(expected_sha256) is not str or SHA256.fullmatch(expected_sha256) is None:
            return _blocked("EXPECTED_DIGEST_INVALID")
        digest = hashlib.sha256(artifact).hexdigest()
        if digest != expected_sha256:
            return _blocked("ARTIFACT_DIGEST_MISMATCH", digest)
        text = artifact.decode("utf-8")
        if any(value in text for value in FORBIDDEN):
            return _blocked("PRIVATE_VALUE_EXPOSURE_BLOCKED", digest)
        parser = _StructureParser()
        parser.feed(text)
        parser.close()
        if parser.forbidden_element or parser.noindex != 1:
            return _blocked("DOCUMENT_SAFETY_INVALID", digest)
        if len(parser.ctas) != 1 or len(parser.disclosures) != 1:
            return _blocked("EXACT_CTA_UNIT_REQUIRED", digest)
        href, rel, target = parser.ctas[0]
        if HREF.fullmatch(href) is None:
            return _blocked("SAME_ORIGIN_CTA_INVALID", digest)
        if set(rel.split()) != {"noopener", "noreferrer", "sponsored"} or target != "_blank":
            return _blocked("CTA_LINK_SAFETY_INVALID", digest)
        if parser.disclosures[0] != contract.DISCLOSURE:
            return _blocked("PR_DISCLOSURE_INVALID", digest)
        if parser.sequence != ["disclosure", "cta"]:
            return _blocked("PR_DISCLOSURE_NOT_PROXIMATE", digest)
        return ArtifactPreflightResult(
            VERSION, PASS, digest, 1, 1, True, True, True, True,
            reason_codes=(
                "OFFLINE_ARTIFACT_STRUCTURALLY_VALID",
                "MANUAL_ACTIVATION_REVIEW_REQUIRED",
            ),
        )
    except (UnicodeDecodeError, ValueError):
        return _blocked("ARTIFACT_PARSE_FAILED")
    except Exception:
        return _blocked("ARTIFACT_PREFLIGHT_ERROR")


__all__ = ["ArtifactPreflightResult", "BLOCKED", "PASS", "VERSION", "review"]
