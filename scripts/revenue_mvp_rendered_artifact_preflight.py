"""Read-only validation and route-bound preflight for reduced-surface HTML."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import revenue_mvp_unordered_surface_review as contract


VERSION = "0.1-candidate"
ALLOWED_TAGS = frozenset({"html", "head", "meta", "title", "body", "main", "h1", "article", "h2", "p", "time", "link", "script", "a", "header", "footer", "nav", "section"})
FORBIDDEN_ATTRIBUTES = frozenset({"srcset", "action", "style", "onclick"})


class ValidationFailure(ValueError):
    pass


class _Inspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_TAGS:
            raise ValidationFailure("TAG_NOT_ALLOWED")
        values = dict(attrs)
        if FORBIDDEN_ATTRIBUTES & set(values) or any(key.startswith("on") for key in values):
            raise ValidationFailure("EXTERNAL_OR_ACTIVE_ATTRIBUTE")
        allowed = {
            "html": {"lang"}, "meta": {"charset", "name", "content"},
            "article": {"class"}, "p": {"class", "id", "role", "aria-live"}, "section": {"class"}, "header": {"class"}, "footer": {"class"}, "a": {"class", "href"}, "main": {"id"}, "nav": {"aria-label"}, "link": {"rel", "href"}, "script": {"src", "defer"},
        }.get(tag, set())
        if not set(values) <= allowed:
            raise ValidationFailure("ATTRIBUTE_NOT_ALLOWED")
        self.tags.append(tag)
        self.attrs.append((tag, values))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())

    def handle_comment(self, data: str) -> None:
        raise ValidationFailure("COMMENT_NOT_ALLOWED")


@dataclass(frozen=True)
class PreflightReceipt:
    version: str
    status: str
    artifact_sha256: str
    candidate_count: int
    target_route: str
    rendered_artifact_validation: str
    route_configuration_review: str
    existing_route_source: str
    rollback_action: str
    explicit_user_approval_required: bool
    public_data_deployment_allowed: bool = False
    publication_allowed: bool = False
    production_activation_allowed: bool = False
    gate_mutation_allowed: bool = False
    cta_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_and_preflight(
    html: bytes, *, expected_sha256: str, expected_count: int,
    target_route: str, repo_root: Path,
) -> PreflightReceipt:
    if hashlib.sha256(html).hexdigest() != expected_sha256 or len(expected_sha256) != 64:
        raise ValidationFailure("ARTIFACT_HASH_MISMATCH")
    if type(expected_count) is not int or expected_count <= 0:
        raise ValidationFailure("CANDIDATE_COUNT_INVALID")
    if target_route != "/items/":
        raise ValidationFailure("TARGET_ROUTE_NOT_REVIEWED")
    try:
        decoded = html.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationFailure("ARTIFACT_ENCODING_INVALID") from error
    inspector = _Inspector()
    inspector.feed(decoded)
    inspector.close()
    allowed_references = {"items.css", "/analytics-consent.css", "/analytics-consent.js", "#main-content", "/about", "/disclosure", "/privacy", "/terms", "/contact", "https://datalabx.jp/items/"}
    for tag, attrs in inspector.attrs:
        reference = attrs.get("href", attrs.get("src"))
        if reference is not None and reference not in allowed_references:
            raise ValidationFailure("EXTERNAL_OR_UNREVIEWED_REFERENCE")
    if inspector.tags.count("article") != expected_count:
        raise ValidationFailure("CANDIDATE_COUNT_MISMATCH")
    if inspector.tags.count("h2") != expected_count or inspector.tags.count("time") != expected_count:
        raise ValidationFailure("ITEM_STRUCTURE_INVALID")
    robots = [attrs for tag, attrs in inspector.attrs if tag == "meta" and attrs.get("name") == "robots"]
    if robots != [{"name": "robots", "content": "noindex,nofollow"}]:
        raise ValidationFailure("ROBOTS_DIRECTIVE_INVALID")
    if inspector.text.count(contract.TRANSPARENCY_NOTICE) != 1:
        raise ValidationFailure("TRANSPARENCY_NOTICE_INVALID")
    required = {"/analytics-consent.css", "/analytics-consent.js", "/about", "/disclosure", "/privacy", "/terms", "/contact", "#main-content", "https://datalabx.jp/items/"}
    links = {attrs.get("href", attrs.get("src")) for _tag, attrs in inspector.attrs}
    if not required <= links or "items.js" in decoded or 'id="result-count" role="status" aria-live="polite"' not in decoded or 'id="page-status" aria-live="polite"' not in decoded:
        raise ValidationFailure("ACCESSIBILITY_OR_CONSENT_CONTRACT_INVALID")
    source = repo_root.resolve() / "items" / "index.html"
    if not source.is_file():
        raise ValidationFailure("TARGET_ROUTE_SOURCE_MISSING")
    return PreflightReceipt(
        VERSION, "READY_FOR_EXPLICIT_ACTIVATION_REVIEW", expected_sha256,
        expected_count, target_route, "PASS", "EXISTING_STATIC_ROUTE_CONFIRMED",
        "items/index.html", "restore_existing_items_index_and_keep_scoped_gate_CLOSED",
        True,
    )


__all__ = ["PreflightReceipt", "ValidationFailure", "validate_and_preflight"]
