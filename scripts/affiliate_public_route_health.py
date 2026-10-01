"""Read-only aggregate health check for the live affiliate CTA surface."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


VERSION = "0.1"
ITEMS_URL = "https://datalabx.jp/items/"
ORIGIN = "https://datalabx.jp"
EXPECTED_CTA_COUNT = 100
EXPECTED_DESTINATION_HOST = "al.fanza.co.jp"
CTA_PATTERN = re.compile(r'href="(/go/itm_[0-9a-f]{24})"')
USER_AGENT = "DATA-LAB-Affiliate-Route-Health/0.1"


@dataclass(frozen=True)
class HealthResult:
    version: str
    status: str
    items_http_status: int | None
    published_cta_count: int
    redirect_http_302_count: int
    redirect_failure_count: int
    destination_host_verified: bool
    external_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def extract_paths(html: str) -> tuple[str, ...]:
    if not isinstance(html, str):
        raise ValueError("html invalid")
    matches = CTA_PATTERN.findall(html)
    if len(matches) != EXPECTED_CTA_COUNT or len(set(matches)) != EXPECTED_CTA_COUNT:
        raise ValueError("cta count invalid")
    return tuple(sorted(matches))


def _fetch_items() -> tuple[int, str]:
    request = urllib.request.Request(ITEMS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return int(response.status), response.read().decode("utf-8")


def _probe(path: str) -> tuple[int, str | None]:
    if CTA_PATTERN.fullmatch(f'href="{path}"') is None:
        raise ValueError("path invalid")
    request = urllib.request.Request(
        ORIGIN + path, method="HEAD", headers={"User-Agent": USER_AGENT}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            status, location = int(response.status), response.headers.get("Location")
    except urllib.error.HTTPError as error:
        status, location = int(error.code), error.headers.get("Location")
    host = None
    if isinstance(location, str):
        parsed = urllib.parse.urlsplit(location)
        if parsed.scheme == "https" and parsed.username is None and parsed.password is None:
            host = parsed.hostname
    return status, host


def run(
    fetch_items: Callable[[], tuple[int, str]] = _fetch_items,
    probe: Callable[[str], tuple[int, str | None]] = _probe,
) -> HealthResult:
    try:
        items_status, html = fetch_items()
        if items_status != 200:
            raise ValueError("items unavailable")
        paths = extract_paths(html)
        with ThreadPoolExecutor(max_workers=5) as executor:
            outcomes = tuple(executor.map(probe, paths))
        redirect_count = sum(
            status == 302 and host == EXPECTED_DESTINATION_HOST
            for status, host in outcomes
        )
        failures = len(outcomes) - redirect_count
        healthy = redirect_count == EXPECTED_CTA_COUNT and failures == 0
        return HealthResult(
            VERSION,
            "HEALTHY" if healthy else "FAILED_SAFE",
            items_status,
            len(paths),
            redirect_count,
            failures,
            healthy,
            False,
            ("ALL_PUBLISHED_AFFILIATE_ROUTES_VERIFIED",) if healthy else
            ("PUBLISHED_AFFILIATE_ROUTE_FAILURE_DETECTED",),
        )
    except Exception:
        return HealthResult(
            VERSION, "FAILED_SAFE", None, 0, 0, 0, False, False,
            ("PUBLIC_ROUTE_HEALTH_CHECK_FAILED",),
        )


def main() -> int:
    result = run()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
