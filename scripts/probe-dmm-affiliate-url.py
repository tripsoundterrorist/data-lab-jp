"""Bounded read-only probe for the DMM API affiliateURL field.

The probe performs at most one API request for one item. It emits booleans and
counts only, never credentials, request URLs, response URLs, titles, or IDs.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import ipaddress
import json
from pathlib import Path
import sys
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
PROBE_VERSION = "0.1"
TIMEOUT_SECONDS = 15

PASS = "PASS"
DRY_RUN_READY = "DRY_RUN_READY"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
ALLOWED_HOST_SUFFIXES = ("dmm.co.jp", "dmm.com", "fanza.com")


@dataclass(frozen=True)
class AffiliateUrlProbeResult:
    probe_version: str
    status: str
    request_performed: bool
    http_success: bool
    api_success: bool
    returned_count: int
    affiliate_link_present: bool
    https_required_pass: bool
    approved_host_pass: bool
    embedded_credentials_absent: bool
    url_length_bounded: bool
    response_persisted: bool
    database_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    requested: bool = False,
    http_success: bool = False,
    api_success: bool = False,
    returned_count: int = 0,
    link_present: bool = False,
    https_pass: bool = False,
    host_pass: bool = False,
    credentials_absent: bool = False,
    length_bounded: bool = False,
    reasons: tuple[str, ...],
) -> AffiliateUrlProbeResult:
    return AffiliateUrlProbeResult(
        PROBE_VERSION,
        status,
        requested,
        http_success,
        api_success,
        returned_count,
        link_present,
        https_pass,
        host_pass,
        credentials_absent,
        length_bounded,
        False,
        False,
        tuple(sorted(set(reasons))),
    )


def load_env_value(path: Path, name: str) -> str | None:
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return value or None
    return None


def _environment(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    api_id = load_env_value(path, "DMM_API_ID")
    affiliate_id = load_env_value(path, "DMM_AFFILIATE_ID")
    if not api_id or not affiliate_id:
        return None
    return api_id, affiliate_id


def _safe_affiliate_url(value: Any) -> tuple[bool, bool, bool, bool, bool]:
    if not isinstance(value, str) or not value:
        return False, False, False, False, False
    if len(value) > 2048:
        return True, False, False, False, False
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return True, False, False, False, True
    except (TypeError, ValueError):
        return True, False, False, False, True

    https_pass = parsed.scheme.casefold() == "https"
    credentials_absent = parsed.username is None and parsed.password is None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    host_pass = (
        bool(hostname)
        and address is None
        and any(
            hostname == suffix or hostname.endswith("." + suffix)
            for suffix in ALLOWED_HOST_SUFFIXES
        )
    )
    return True, https_pass, host_pass, credentials_absent, True


def run_probe(
    *,
    env_path: Path = ENV_PATH,
    dry_run: bool = False,
    fetcher: Callable[..., Any] = urllib.request.urlopen,
) -> AffiliateUrlProbeResult:
    """Run zero or one request and return only a bounded safe summary."""

    try:
        environment = _environment(env_path)
        if environment is None:
            return _result(
                BLOCKED, reasons=("REQUIRED_ENVIRONMENT_NOT_CONFIGURED",)
            )
        if dry_run:
            return _result(
                DRY_RUN_READY, reasons=("DRY_RUN_ENVIRONMENT_READY",)
            )

        api_id, affiliate_id = environment
        parameters = {
            "api_id": api_id,
            "affiliate_id": affiliate_id,
            "site": "FANZA",
            "service": "digital",
            "floor": "videoa",
            "hits": 1,
            "offset": 1,
            "sort": "date",
            "output": "json",
        }
        request = urllib.request.Request(
            ENDPOINT + "?" + urllib.parse.urlencode(parameters),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with fetcher(request, timeout=TIMEOUT_SECONDS) as response:
                http_status = response.status
                payload = json.load(response)
        except urllib.error.HTTPError:
            return _result(
                BLOCKED,
                requested=True,
                reasons=("API_HTTP_ERROR",),
            )
        except (urllib.error.URLError, TimeoutError):
            return _result(
                BLOCKED,
                requested=True,
                reasons=("API_REQUEST_FAILED",),
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _result(
                BLOCKED,
                requested=True,
                reasons=("API_RESPONSE_JSON_INVALID",),
            )

        http_success = isinstance(http_status, int) and 200 <= http_status < 300
        if not http_success:
            return _result(
                BLOCKED,
                requested=True,
                reasons=("API_HTTP_STATUS_NOT_SUCCESS",),
            )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or str(result.get("status")) != "200":
            return _result(
                BLOCKED,
                requested=True,
                http_success=True,
                reasons=("API_RESULT_STATUS_INVALID",),
            )
        items = result.get("items")
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            count = len(items) if isinstance(items, list) and len(items) <= 1 else 0
            return _result(
                BLOCKED,
                requested=True,
                http_success=True,
                api_success=True,
                returned_count=count,
                reasons=("API_SINGLE_ITEM_REQUIRED",),
            )

        present, https_pass, host_pass, credentials_absent, length_bounded = (
            _safe_affiliate_url(items[0].get("affiliateURL"))
        )
        passed = all(
            (present, https_pass, host_pass, credentials_absent, length_bounded)
        )
        reasons: list[str] = []
        if not present:
            reasons.append("AFFILIATE_LINK_NOT_PRESENT")
        if present and not https_pass:
            reasons.append("AFFILIATE_LINK_HTTPS_REQUIRED")
        if present and not host_pass:
            reasons.append("AFFILIATE_LINK_HOST_NOT_APPROVED")
        if present and not credentials_absent:
            reasons.append("AFFILIATE_LINK_EMBEDDED_CREDENTIALS")
        if not length_bounded:
            reasons.append("AFFILIATE_LINK_LENGTH_INVALID")
        return _result(
            PASS if passed else BLOCKED,
            requested=True,
            http_success=True,
            api_success=True,
            returned_count=1,
            link_present=present,
            https_pass=https_pass,
            host_pass=host_pass,
            credentials_absent=credentials_absent,
            length_bounded=length_bounded,
            reasons=tuple(reasons) or ("AFFILIATE_LINK_SAFE_SHAPE_CONFIRMED",),
        )
    except Exception:
        return _result(
            FAIL_CLOSED,
            reasons=("AFFILIATE_URL_PROBE_INTERNAL_ERROR",),
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe one DMM item without printing identifiers or URLs."
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_probe(env_path=ENV_PATH, dry_run=args.dry_run)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {PASS, DRY_RUN_READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
