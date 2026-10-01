"""Read-only aggregate health check for published official product images."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from html import unescape
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable


VERSION = "0.1"
ITEMS_URL = "https://datalabx.jp/items/"
EXPECTED_IMAGE_COUNT = 100
EXPECTED_IMAGE_HOST = "pics.dmm.co.jp"
IMAGE_PATTERN = re.compile(r'<img class="card-image" src="([^"]+)"')
USER_AGENT = "DATA-LAB-Product-Image-Health/0.1"


@dataclass(frozen=True)
class HealthResult:
    version: str
    status: str
    items_http_status: int | None
    published_image_count: int
    healthy_image_count: int
    image_failure_count: int
    official_host_verified: bool
    external_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def extract_urls(html: str) -> tuple[str, ...]:
    if not isinstance(html, str):
        raise ValueError("html invalid")
    matches = tuple(unescape(value) for value in IMAGE_PATTERN.findall(html))
    if len(matches) != EXPECTED_IMAGE_COUNT or len(set(matches)) != EXPECTED_IMAGE_COUNT:
        raise ValueError("image count invalid")
    for value in matches:
        parsed = urllib.parse.urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != EXPECTED_IMAGE_HOST
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("image url invalid")
    return tuple(sorted(matches))


def _fetch_items() -> tuple[int, str]:
    request = urllib.request.Request(ITEMS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return int(response.status), response.read().decode("utf-8")


def _probe(url: str) -> tuple[int, str | None]:
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return int(response.status), response.headers.get("Content-Type")


def run(
    fetch_items: Callable[[], tuple[int, str]] = _fetch_items,
    probe: Callable[[str], tuple[int, str | None]] = _probe,
) -> HealthResult:
    try:
        items_status, html = fetch_items()
        if items_status != 200:
            raise ValueError("items unavailable")
        urls = extract_urls(html)
        with ThreadPoolExecutor(max_workers=5) as executor:
            outcomes = tuple(executor.map(probe, urls))
        healthy_count = sum(
            status in {200, 206}
            and isinstance(content_type, str)
            and content_type.casefold().startswith("image/")
            for status, content_type in outcomes
        )
        failures = len(outcomes) - healthy_count
        healthy = healthy_count == EXPECTED_IMAGE_COUNT and failures == 0
        return HealthResult(
            VERSION,
            "HEALTHY" if healthy else "FAILED_SAFE",
            items_status,
            len(urls),
            healthy_count,
            failures,
            healthy,
            False,
            ("ALL_PUBLISHED_OFFICIAL_IMAGES_VERIFIED",) if healthy else
            ("PUBLISHED_IMAGE_FAILURE_DETECTED",),
        )
    except Exception:
        return HealthResult(
            VERSION, "FAILED_SAFE", None, 0, 0, 0, False, False,
            ("PUBLIC_IMAGE_HEALTH_CHECK_FAILED",),
        )


def main() -> int:
    result = run()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
