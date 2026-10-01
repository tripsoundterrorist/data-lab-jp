"""Read-only SEO quality review for the staged 300-item expansion design."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


VERSION = "0.1"
REVIEWED = "SEO_QUALITY_REVIEWED_KEEP_NOINDEX"
BLOCKED = "SEO_QUALITY_REVIEW_BLOCKED"
ROOT = Path(__file__).resolve().parents[1]
CURRENT_ITEM_COUNT = 100
TARGET_ITEM_COUNT = 300
PUBLIC_ID_ROUTE = re.compile(r"/go/(itm_[0-9a-f]{24})\Z")


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.robots: list[str] = []
        self.canonicals: list[str] = []
        self.article_count = 0
        self.h2_count = 0
        self.image_count = 0
        self.price_count = 0
        self.time_count = 0
        self.disclosure_count = 0
        self.cta_ids: list[str] = []
        self._article_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        classes = values.get("class", "").split()
        lowered = tag.casefold()
        if lowered == "meta" and values.get("name", "").casefold() == "robots":
            self.robots.append(values.get("content", "").casefold())
        if lowered == "link" and values.get("rel", "").casefold() == "canonical":
            self.canonicals.append(values.get("href", ""))
        if lowered == "article" and "item" in classes:
            self.article_count += 1
            self._article_depth += 1
        elif self._article_depth:
            if lowered == "h2":
                self.h2_count += 1
            elif lowered == "img" and "card-image" in classes:
                self.image_count += 1
            elif lowered == "p" and "price" in classes:
                self.price_count += 1
            elif lowered == "time":
                self.time_count += 1
            elif lowered == "p" and "affiliate-cta-disclosure" in classes:
                self.disclosure_count += 1
            elif lowered == "a" and "affiliate-cta-link" in classes:
                match = PUBLIC_ID_ROUTE.fullmatch(values.get("href", ""))
                if match:
                    self.cta_ids.append(match.group(1))

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "article" and self._article_depth:
            self._article_depth -= 1


@dataclass(frozen=True)
class SeoQualityReview:
    version: str
    status: str
    current_item_count: int
    target_item_count: int
    complete_card_count: int
    unique_cta_route_count: int
    seo_quality_reviewed: bool
    indexing_allowed: bool
    detail_page_generation_allowed: bool
    sitemap_change_allowed: bool
    publication_allowed: bool
    candidate_render_performance_verified: bool
    source_sha256: dict[str, str]
    reason_codes: tuple[str, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["recommendations"] = list(self.recommendations)
        return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(root: Path = ROOT) -> SeoQualityReview:
    listing = root / "items" / "index.html"
    template = root / "items" / "item.html"
    sitemap = root / "sitemap.xml"
    reasons: set[str] = set()
    hashes: dict[str, str] = {}
    parser = _ListingParser()
    try:
        for name, path in {
            "items/index.html": listing,
            "items/item.html": template,
            "sitemap.xml": sitemap,
        }.items():
            if not path.is_file():
                raise OSError("source missing")
            hashes[name] = _sha256(path)
        parser.feed(listing.read_text(encoding="utf-8"))
        parser.close()
        template_text = template.read_text(encoding="utf-8")
        sitemap_text = sitemap.read_text(encoding="utf-8")

        if parser.robots != ["noindex,nofollow"]:
            reasons.add("LISTING_NOINDEX_MISSING")
        if parser.canonicals != ["https://datalabx.jp/items/"]:
            reasons.add("LISTING_CANONICAL_INVALID")
        if 'name="robots" content="noindex,nofollow"' not in template_text:
            reasons.add("TEMPLATE_NOINDEX_MISSING")
        if "https://datalabx.jp/items" in sitemap_text:
            reasons.add("ITEM_SURFACE_IN_SITEMAP")
        if parser.article_count != CURRENT_ITEM_COUNT:
            reasons.add("CURRENT_ITEM_COUNT_NOT_EXACT")
        card_counts = {
            parser.h2_count, parser.image_count, parser.price_count,
            parser.time_count, parser.disclosure_count, len(parser.cta_ids),
        }
        if card_counts != {CURRENT_ITEM_COUNT}:
            reasons.add("CARD_STRUCTURE_INCOMPLETE")
        if len(set(parser.cta_ids)) != len(parser.cta_ids):
            reasons.add("CTA_ROUTE_DUPLICATE")
    except (OSError, UnicodeError, ValueError):
        reasons.add("SEO_SOURCE_EVIDENCE_INVALID")

    reviewed = not reasons
    return SeoQualityReview(
        VERSION,
        REVIEWED if reviewed else BLOCKED,
        parser.article_count,
        TARGET_ITEM_COUNT,
        min(
            parser.article_count, parser.h2_count, parser.image_count,
            parser.price_count, parser.time_count, parser.disclosure_count,
            len(parser.cta_ids),
        ),
        len(set(parser.cta_ids)),
        reviewed,
        False,
        False,
        False,
        False,
        False,
        hashes,
        tuple(sorted(reasons)),
        (
            "KEEP_ITEM_SURFACE_NOINDEX_UNTIL_SEPARATE_INDEXING_REVIEW",
            "DO_NOT_GENERATE_THIN_ITEM_DETAIL_PAGES",
            "VERIFY_300_ITEM_RENDER_PERFORMANCE_BEFORE_PUBLICATION",
        ),
    )


def main() -> int:
    result = review()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == REVIEWED else 2


if __name__ == "__main__":
    raise SystemExit(main())
