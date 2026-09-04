"""Read-only Search Console preflight for the Revenue MVP public shell."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://datalabx.jp"
GATE_VERSION = "0.1"
READY = "PUBLIC_SHELL_READY"
FAIL_CLOSED = "FAIL_CLOSED"
INDEXABLE = {
    "index.html": f"{ORIGIN}/",
    "column-price.html": f"{ORIGIN}/column-price",
    "column-trend.html": f"{ORIGIN}/column-trend",
    "column-score.html": f"{ORIGIN}/column-score",
    "about.html": f"{ORIGIN}/about",
    "disclosure.html": f"{ORIGIN}/disclosure",
    "privacy.html": f"{ORIGIN}/privacy",
    "terms.html": f"{ORIGIN}/terms",
    "contact.html": f"{ORIGIN}/contact",
}


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "link" and values.get("rel") == "canonical":
            self.meta["canonical"] = values.get("href") or ""
        elif tag == "meta":
            key = values.get("name") or values.get("property")
            if key:
                self.meta[key] = values.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


@dataclass(frozen=True)
class SearchConsoleGateResult:
    gate_version: str
    status: str
    search_console_write_performed: bool
    public_shell_indexing_allowed: bool
    item_indexing_allowed: bool
    indexable_url_count: int
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def _parse(path: Path) -> tuple[MetadataParser, str]:
    document = path.read_text(encoding="utf-8")
    parser = MetadataParser()
    parser.feed(document)
    return parser, document


def run_gate(root: Path = ROOT) -> SearchConsoleGateResult:
    reasons: set[str] = set()
    try:
        for filename, canonical in INDEXABLE.items():
            parser, document = _parse(root / filename)
            if not parser.title.strip():
                reasons.add("TITLE_MISSING")
            if not parser.meta.get("description", "").strip():
                reasons.add("DESCRIPTION_MISSING")
            if parser.meta.get("canonical") != canonical:
                reasons.add("CANONICAL_MISMATCH")
            if parser.meta.get("robots", "").casefold().find("noindex") >= 0:
                reasons.add("INDEXABLE_PAGE_NOINDEXED")
            if "pages.dev" in document or canonical.endswith(".html"):
                reasons.add("LEGACY_OR_NONCANONICAL_URL")
            for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                document,
                flags=re.DOTALL,
            ):
                json.loads(block)

        sitemap = ET.parse(root / "sitemap.xml").getroot()
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = {node.text for node in sitemap.findall("s:url/s:loc", namespace)}
        if locations != set(INDEXABLE.values()):
            reasons.add("SITEMAP_MISMATCH")

        robots = (root / "robots.txt").read_text(encoding="utf-8")
        if "User-agent: *" not in robots or f"Sitemap: {ORIGIN}/sitemap.xml" not in robots:
            reasons.add("ROBOTS_INVALID")

        not_indexable = ("404.html", "items/index.html", "items/item.html")
        for filename in not_indexable:
            parser, _ = _parse(root / filename)
            if "noindex" not in parser.meta.get("robots", "").casefold():
                reasons.add("PRIVATE_ROUTE_INDEXABLE")
    except Exception:
        reasons.add("SEO_GATE_INPUT_OR_INTERNAL_ERROR")

    ready = not reasons
    return SearchConsoleGateResult(
        GATE_VERSION,
        READY if ready else FAIL_CLOSED,
        False,
        ready,
        False,
        len(INDEXABLE) if ready else 0,
        tuple(sorted(reasons)) or ("PUBLIC_SHELL_SEO_VALIDATED", "ITEM_INDEXING_BLOCKED"),
        (
            "SUBMIT_SITEMAP_IN_SEARCH_CONSOLE",
            "REQUEST_HOME_URL_INSPECTION",
            "DO_NOT_REQUEST_ITEM_INDEXING",
        ) if ready else ("FIX_SEO_GATE_FAILURE",),
    )


def main() -> int:
    result = run_gate()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
