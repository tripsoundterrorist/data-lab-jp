"""Read-only HTTP smoke gate for the deployed Revenue MVP shell."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
import json
import socket
from typing import Callable, Mapping
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


ORIGIN = "https://datalabx.jp"
GATE_VERSION = "0.2"
PASS = "PRODUCTION_SHELL_VALIDATED"
FAIL_CLOSED = "FAIL_CLOSED"
INDEXABLE = {
    "/": f"{ORIGIN}/",
    "/column-price": f"{ORIGIN}/column-price",
    "/column-trend": f"{ORIGIN}/column-trend",
    "/column-score": f"{ORIGIN}/column-score",
    "/about": f"{ORIGIN}/about",
    "/disclosure": f"{ORIGIN}/disclosure",
    "/privacy": f"{ORIGIN}/privacy",
    "/terms": f"{ORIGIN}/terms",
    "/contact": f"{ORIGIN}/contact",
}
PRIVATE = ("/items/", "/items/item")
NOT_FOUND = "/__data_lab_release_smoke_missing__"


@dataclass(frozen=True)
class HttpEvidence:
    status: int
    final_url: str
    body: str


@dataclass(frozen=True)
class ProductionSmokeResult:
    gate_version: str
    status: str
    production_write_performed: bool
    checked_url_count: int
    failed_url_count: int
    failed_check_group_count: int
    indexable_url_count: int
    item_indexing_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


class _Metadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonical = ""
        self.robots = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href") or ""
        if tag == "meta" and values.get("name") == "robots":
            self.robots = values.get("content") or ""


def _fetch(path: str) -> HttpEvidence:
    request = urllib.request.Request(
        ORIGIN + path, headers={"User-Agent": "DATA-LAB-Revenue-MVP-Smoke/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return HttpEvidence(
                response.status, response.geturl(), response.read(1_000_000).decode("utf-8")
            )
    except urllib.error.HTTPError as error:
        return HttpEvidence(
            error.code, error.geturl(), error.read(1_000_000).decode("utf-8")
        )


def validate_responses(responses: Mapping[str, HttpEvidence]) -> ProductionSmokeResult:
    reasons: set[str] = set()
    expected_paths = set(INDEXABLE) | set(PRIVATE) | {"/robots.txt", "/sitemap.xml", NOT_FOUND}
    if set(responses) != expected_paths:
        reasons.add("INCOMPLETE_EVIDENCE")
    for path, canonical in INDEXABLE.items():
        evidence = responses.get(path)
        if evidence is None:
            continue
        parser = _Metadata()
        parser.feed(evidence.body)
        if evidence.status != 200:
            reasons.add("PUBLIC_PAGE_HTTP_FAILURE")
        if evidence.final_url != canonical or parser.canonical != canonical:
            reasons.add("PUBLIC_CANONICAL_MISMATCH")
        if "noindex" in parser.robots.casefold():
            reasons.add("PUBLIC_PAGE_NOINDEXED")
    for path in PRIVATE:
        evidence = responses.get(path)
        if evidence is None:
            continue
        parser = _Metadata()
        parser.feed(evidence.body)
        if evidence.status != 200 or "noindex" not in parser.robots.casefold():
            reasons.add("PRIVATE_ROUTE_EXPOSED_OR_UNAVAILABLE")
    missing = responses.get(NOT_FOUND)
    if missing is not None:
        parser = _Metadata()
        parser.feed(missing.body)
        if missing.status != 404 or "noindex" not in parser.robots.casefold():
            reasons.add("CUSTOM_404_INVALID")
    robots = responses.get("/robots.txt")
    if robots is not None and (
        robots.status != 200 or f"Sitemap: {ORIGIN}/sitemap.xml" not in robots.body
    ):
        reasons.add("ROBOTS_INVALID")
    sitemap = responses.get("/sitemap.xml")
    if sitemap is not None:
        try:
            root = ET.fromstring(sitemap.body)
            namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locations = {node.text for node in root.findall("s:url/s:loc", namespace)}
            if sitemap.status != 200 or locations != set(INDEXABLE.values()):
                reasons.add("SITEMAP_INVALID")
        except ET.ParseError:
            reasons.add("SITEMAP_INVALID")
    return ProductionSmokeResult(
        GATE_VERSION, PASS if not reasons else FAIL_CLOSED, False,
        len(responses), 0, 0, len(INDEXABLE) if not reasons else 0, False,
        tuple(sorted(reasons)) or ("PRODUCTION_HTTP_VALIDATED", "ITEM_INDEXING_BLOCKED"),
    )


def run_gate(fetcher: Callable[[str], HttpEvidence] = _fetch) -> ProductionSmokeResult:
    paths = (*INDEXABLE, *PRIVATE, "/robots.txt", "/sitemap.xml", NOT_FOUND)
    responses: dict[str, HttpEvidence] = {}
    failed_groups: set[str] = set()
    failed_url_count = 0

    def failure_group(path: str) -> str:
        if path == "/":
            return "PUBLIC_HOME_FETCH_FAILED"
        if path.startswith("/column-"):
            return "PUBLIC_COLUMN_FETCH_FAILED"
        if path in INDEXABLE:
            return "PUBLIC_INFORMATION_FETCH_FAILED"
        if path in PRIVATE:
            return "PRIVATE_ROUTE_FETCH_FAILED"
        if path in {"/robots.txt", "/sitemap.xml"}:
            return "SEO_ASSET_FETCH_FAILED"
        return "NOT_FOUND_ROUTE_FETCH_FAILED"

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            pending = {executor.submit(fetcher, path): path for path in paths}
            for future in as_completed(pending):
                path = pending[future]
                try:
                    responses[path] = future.result()
                except (
                    OSError, UnicodeError, urllib.error.URLError,
                    socket.timeout, ValueError,
                ):
                    failed_url_count += 1
                    failed_groups.add(failure_group(path))
                except Exception:
                    failed_url_count += 1
                    failed_groups.add("PRODUCTION_HTTP_INTERNAL_ERROR")
        validated = validate_responses(responses)
        reasons = set(validated.reason_codes) if validated.status != PASS else set()
        reasons.update(failed_groups)
        if failed_groups:
            reasons.add("PRODUCTION_HTTP_CHECK_FAILED")
        return ProductionSmokeResult(
            GATE_VERSION, PASS if not reasons else FAIL_CLOSED, False,
            len(responses), failed_url_count, len(failed_groups),
            len(INDEXABLE) if not reasons else 0, False,
            tuple(sorted(reasons)) or (
                "PRODUCTION_HTTP_VALIDATED", "ITEM_INDEXING_BLOCKED",
            ),
        )
    except Exception:
        return ProductionSmokeResult(
            GATE_VERSION, FAIL_CLOSED, False, len(responses), 1, 1, 0, False,
            ("PRODUCTION_HTTP_CHECK_FAILED", "PRODUCTION_HTTP_INTERNAL_ERROR"),
        )


def main() -> int:
    result = run_gate()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
