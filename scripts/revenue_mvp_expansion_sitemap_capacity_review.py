"""Read-only sitemap capacity review for the 300-item expansion candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


VERSION = "0.1"
VERIFIED = "SITEMAP_CAPACITY_VERIFIED"
BLOCKED = "BLOCKED"
ROOT = Path(__file__).resolve().parents[1]
SITEMAP_LIMIT = 50_000
TARGET_ITEM_COUNT = 300


class _HeadSignals(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.robots: list[str] = []
        self.canonicals: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value for key, value in attrs}
        if tag.casefold() == "meta" and values.get("name", "").casefold() == "robots":
            if values.get("content") is not None:
                self.robots.append(values["content"].casefold())
        if tag.casefold() == "link" and values.get("rel", "").casefold() == "canonical":
            if values.get("href") is not None:
                self.canonicals.append(values["href"])


@dataclass(frozen=True)
class SitemapCapacityReview:
    version: str
    status: str
    target_item_count: int
    sitemap_url_count: int
    sitemap_limit: int
    target_additional_sitemap_urls: int
    sitemap_capacity_verified: bool
    seo_quality_reviewed: bool
    publication_allowed: bool
    sitemap_change_allowed: bool
    source_sha256: dict[str, str]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _head_signals(path: Path) -> _HeadSignals:
    parser = _HeadSignals()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def review(root: Path = ROOT) -> SitemapCapacityReview:
    files = {
        "sitemap.xml": root / "sitemap.xml",
        "robots.txt": root / "robots.txt",
        "items/index.html": root / "items" / "index.html",
        "items/item.html": root / "items" / "item.html",
    }
    reasons: set[str] = set()
    hashes: dict[str, str] = {}
    sitemap_count = 0
    try:
        if any(not path.is_file() for path in files.values()):
            raise ValueError("required source missing")
        hashes = {name: _sha256(path) for name, path in files.items()}

        sitemap_root = ET.parse(files["sitemap.xml"]).getroot()
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        if sitemap_root.tag != namespace + "urlset":
            reasons.add("SITEMAP_ROOT_INVALID")
        locations = [
            node.text for node in sitemap_root.findall(f"{namespace}url/{namespace}loc")
        ]
        if any(not isinstance(value, str) or not value.startswith("https://datalabx.jp/")
               for value in locations):
            reasons.add("SITEMAP_LOCATION_INVALID")
        if len(locations) != len(set(locations)):
            reasons.add("SITEMAP_LOCATION_DUPLICATE")
        sitemap_count = len(locations)
        if sitemap_count > SITEMAP_LIMIT:
            reasons.add("SITEMAP_LIMIT_EXCEEDED")
        if any("/items" in value for value in locations if isinstance(value, str)):
            reasons.add("ITEM_SURFACE_UNEXPECTEDLY_INDEXED")

        robots = files["robots.txt"].read_text(encoding="utf-8")
        if "Sitemap: https://datalabx.jp/sitemap.xml" not in robots:
            reasons.add("ROBOTS_SITEMAP_REFERENCE_MISSING")
        if "Disallow: /preview/" not in robots:
            reasons.add("PREVIEW_ROBOTS_BLOCK_MISSING")

        listing = _head_signals(files["items/index.html"])
        template = _head_signals(files["items/item.html"])
        if listing.robots != ["noindex,nofollow"]:
            reasons.add("ITEM_LISTING_NOINDEX_MISSING")
        if template.robots != ["noindex,nofollow"]:
            reasons.add("ITEM_TEMPLATE_NOINDEX_MISSING")
        if listing.canonicals != ["https://datalabx.jp/items/"]:
            reasons.add("ITEM_LISTING_CANONICAL_INVALID")
        if template.canonicals != ["https://datalabx.jp/items/item"]:
            reasons.add("ITEM_TEMPLATE_CANONICAL_INVALID")
    except (OSError, UnicodeError, ValueError, ET.ParseError):
        reasons.add("SOURCE_EVIDENCE_INVALID")

    verified = not reasons
    return SitemapCapacityReview(
        VERSION,
        VERIFIED if verified else BLOCKED,
        TARGET_ITEM_COUNT,
        sitemap_count,
        SITEMAP_LIMIT,
        0,
        verified,
        False,
        False,
        False,
        hashes,
        tuple(sorted(reasons)),
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        result = SitemapCapacityReview(
            VERSION, BLOCKED, TARGET_ITEM_COUNT, 0, SITEMAP_LIMIT, 0,
            False, False, False, False, {}, ("ARGUMENTS_NOT_SUPPORTED",),
        )
    else:
        result = review()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == VERIFIED else 2


if __name__ == "__main__":
    raise SystemExit(main())
