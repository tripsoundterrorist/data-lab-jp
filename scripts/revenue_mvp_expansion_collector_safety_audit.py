"""Static fail-closed safety audit of the collector used by expansion planning."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "0.1"
PASS = "PASS"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SafetyAudit:
    version: str
    status: str
    source_sha256: str | None
    request_interval_seconds: float | None
    timeout_seconds: int | None
    http_error_stops: bool
    url_error_stops: bool
    response_validation_precedes_writes: bool
    retry_loop_detected: bool
    api_calls: int
    database_writes: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _constant(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    return None
    return None


def assess(source: Path) -> SafetyAudit:
    try:
        if source.is_symlink() or not source.is_file():
            raise ValueError("SOURCE_INVALID")
        raw = source.read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text)
        interval = _constant(tree, "REQUEST_INTERVAL_SECONDS")
        timeout = _constant(tree, "TIMEOUT_SECONDS")
        reasons: set[str] = set()
        if type(interval) not in {int, float} or isinstance(interval, bool) or interval < 1.0:
            reasons.add("REQUEST_INTERVAL_UNSAFE")
        if type(timeout) is not int or isinstance(timeout, bool) or not 1 <= timeout <= 30:
            reasons.add("TIMEOUT_UNBOUNDED")

        http_stop = (
            "except urllib.error.HTTPError as error:" in text
            and 'raise CollectionFailure(' in text
            and '"HTTP_ERROR"' in text
        )
        url_stop = (
            "except (urllib.error.URLError, TimeoutError):" in text
            and '"API_REQUEST_FAILED"' in text
        )
        if not http_stop:
            reasons.add("HTTP_ERROR_STOP_UNVERIFIED")
        if not url_stop:
            reasons.add("NETWORK_ERROR_STOP_UNVERIFIED")

        request_line = text.find("with urllib.request.urlopen(")
        validation_line = text.find("page_result_count = parse_optional_int")
        write_line = text.find("with connection:", request_line)
        ordering = 0 <= request_line < validation_line < write_line
        if not ordering:
            reasons.add("PREWRITE_VALIDATION_ORDER_UNVERIFIED")

        retry_markers = ("Retry(", "retry_count", "for retry", "while retry")
        retry_detected = any(marker in text for marker in retry_markers)
        if retry_detected:
            reasons.add("RETRY_LOGIC_DETECTED")

        return SafetyAudit(
            VERSION, PASS if not reasons else BLOCKED,
            hashlib.sha256(raw).hexdigest(),
            float(interval) if type(interval) in {int, float} and not isinstance(interval, bool) else None,
            timeout if type(timeout) is int and not isinstance(timeout, bool) else None,
            http_stop, url_stop, ordering, retry_detected, 0, 0,
            tuple(sorted(reasons)),
        )
    except (OSError, UnicodeError, SyntaxError, ValueError):
        return SafetyAudit(
            VERSION, BLOCKED, None, None, None, False, False, False, False,
            0, 0, ("SAFETY_AUDIT_FAILED",),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", required=True, type=Path)
    args = parser.parse_args(argv)
    result = assess(args.collector)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
