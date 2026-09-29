"""Bounded local DMM-to-D1 lifecycle revalidation transport.

The CLI is dry-run by default. A live cycle requires both --execute and the
exact confirmation token. Output is aggregate-only and never contains IDs,
credentials, request URLs, affiliate URLs, response bodies, or SQL.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable
import urllib.parse

from affiliate_runtime_dmm_connector import (
    AffiliateRuntimeConnectorError,
    fetch_item_response,
)


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
WRANGLER_CONFIG = ROOT / "deployment-candidates" / "affiliate-worker" / "wrangler.toml"
DATABASE_NAME = "data-lab-affiliate-lookup"
VERSION = "0.1"
BATCH_SIZE = 5
CONFIRMATION = "LIVE_LOCAL_DMM_D1_REVALIDATION"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
CONTENT_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
ALLOWED_HOSTS = ("dmm.com", "dmm.co.jp", "fanza.com", "fanza.co.jp")
SELECT_SQL = (
    "SELECT public_id,content_id FROM affiliate_item_lookup "
    "WHERE rights_status='CONDITIONALLY_APPROVED' AND lifecycle_status='RESOLVED' "
    "ORDER BY updated_at ASC,public_id ASC LIMIT 5"
)


@dataclass(frozen=True)
class Result:
    version: str
    status: str
    mode: str
    selected: int
    valid: int
    disabled: int
    database_write_performed: bool
    temporary_sql_deleted: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, mode: str, reason: str, **values: Any) -> Result:
    defaults = {
        "selected": 0,
        "valid": 0,
        "disabled": 0,
        "database_write_performed": False,
        "temporary_sql_deleted": True,
    }
    defaults.update(values)
    return Result(VERSION, status, mode, reason_codes=(reason,), **defaults)


def _wrangler(arguments: list[str], runner: Callable[..., Any] = subprocess.run) -> Any:
    return runner(
        ["npx.cmd", "wrangler", *arguments, "--config", str(WRANGLER_CONFIG)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _json_payload(stdout: Any) -> Any:
    if not isinstance(stdout, str):
        raise ValueError("output invalid")
    stripped = stdout.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return json.loads(stripped)
    marker = stdout.find("\n[")
    if marker < 0:
        marker = stdout.find("\r\n[")
    if marker < 0:
        raise ValueError("output invalid")
    return json.loads(stdout[marker + (2 if stdout.startswith("\r\n", marker) else 1):])


def _select(runner: Callable[..., Any]) -> list[dict[str, str]]:
    process = _wrangler(
        ["d1", "execute", DATABASE_NAME, "--remote", "--json", "--command", SELECT_SQL],
        runner,
    )
    payload = _json_payload(process.stdout)
    if not isinstance(payload, list) or len(payload) != 1 or payload[0].get("success") is not True:
        raise RuntimeError("selection invalid")
    rows = payload[0].get("results")
    if not isinstance(rows, list) or len(rows) > BATCH_SIZE:
        raise RuntimeError("selection invalid")
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"public_id", "content_id"}
                or not isinstance(row["public_id"], str) or not PUBLIC_ID.fullmatch(row["public_id"])
                or not isinstance(row["content_id"], str) or not CONTENT_ID.fullmatch(row["content_id"])):
            raise RuntimeError("selection invalid")
    return rows


def _write_succeeded(process: Any) -> bool:
    try:
        payload = _json_payload(process.stdout)
        return (isinstance(payload, list) and len(payload) >= 1
                and all(entry.get("success") is True for entry in payload))
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _safe_url(value: Any) -> bool:
    try:
        if not isinstance(value, str) or not 12 <= len(value) <= 4096:
            return False
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or "").casefold().rstrip(".")
        return (
            parsed.scheme == "https" and parsed.username is None and parsed.password is None
            and parsed.port is None and not any(ord(char) <= 32 or ord(char) == 127 for char in value)
            and any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS)
        )
    except (TypeError, ValueError):
        return False


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _statements(rows: list[dict[str, str]], outcomes: list[tuple[str, str | None]], checked_at: str) -> str:
    statements: list[str] = []
    for row, (outcome, affiliate_url) in zip(rows, outcomes, strict=True):
        public_id, content_id = _quote(row["public_id"]), _quote(row["content_id"])
        checked = _quote(checked_at)
        if outcome == "VALID" and affiliate_url is not None:
            # Fail closed if remote file execution stops part-way: target and
            # audit are written before the final enable transition.
            statements.extend((
                "INSERT INTO affiliate_redirect_target (public_id,content_id,affiliate_url,verified_at) "
                f"VALUES ({public_id},{content_id},{_quote(affiliate_url)},{checked}) ON CONFLICT(public_id) "
                "DO UPDATE SET content_id=excluded.content_id,affiliate_url=excluded.affiliate_url,"
                "verified_at=excluded.verified_at;",
                "INSERT INTO affiliate_lifecycle_revalidation_event "
                "(public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
                f"VALUES ({public_id},{checked},'VALID',1,'OFFICIAL_API_EXACT_MATCH');",
                "UPDATE affiliate_item_lookup SET verification_status='PASS',affiliate_enabled=1,"
                f"updated_at={checked} WHERE public_id={public_id} AND content_id={content_id} "
                "AND rights_status='CONDITIONALLY_APPROVED' AND lifecycle_status='RESOLVED';",
            ))
        else:
            reason = "OFFICIAL_API_ITEM_UNAVAILABLE" if outcome == "NOT_AVAILABLE" else "LOCAL_UPSTREAM_UNCONFIRMED"
            verification = "FAILED" if outcome == "NOT_AVAILABLE" else "PENDING"
            statements.extend((
                f"UPDATE affiliate_item_lookup SET verification_status='{verification}',affiliate_enabled=0,"
                f"updated_at={checked} WHERE public_id={public_id} AND content_id={content_id};",
                "INSERT INTO affiliate_lifecycle_revalidation_event "
                "(public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
                f"VALUES ({public_id},{checked},{_quote(outcome)},0,{_quote(reason)});",
            ))
    return "\n".join(statements) + "\n"


def run_cycle(*, execute: bool = False, confirmed: bool = False,
              runner: Callable[..., Any] = subprocess.run,
              fetcher: Callable[..., Any] | None = None,
              checked_at: str | None = None) -> Result:
    mode = "LIVE" if execute else "DRY_RUN"
    temporary_path: Path | None = None
    try:
        if execute and not confirmed:
            return _result("BLOCKED", mode, "EXPLICIT_CONFIRMATION_REQUIRED")
        if not ENV_PATH.is_file() or not WRANGLER_CONFIG.is_file():
            return _result("BLOCKED", mode, "REQUIRED_LOCAL_STATE_UNAVAILABLE")
        rows = _select(runner)
        if not execute:
            return _result("READY", mode, "BOUNDED_SELECTION_VALIDATED", selected=len(rows))
        if not rows:
            return _result("COMPLETED", mode, "NO_ELIGIBLE_ROWS")

        outcomes: list[tuple[str, str | None]] = []
        for row in rows:
            try:
                kwargs = {"content_id": row["content_id"], "env_path": ENV_PATH}
                if fetcher is not None:
                    kwargs["fetcher"] = fetcher
                payload = fetch_item_response(**kwargs)
                items = payload.get("result", {}).get("items")
                if isinstance(items, list) and len(items) == 1 and items[0].get("content_id") == row["content_id"]:
                    affiliate_url = items[0].get("affiliateURL")
                    outcomes.append(("VALID", affiliate_url) if _safe_url(affiliate_url) else ("NOT_AVAILABLE", None))
                else:
                    outcomes.append(("NOT_AVAILABLE", None))
            except AffiliateRuntimeConnectorError:
                outcomes.append(("UNCONFIRMED", None))

        timestamp = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            return _result("BLOCKED", mode, "CHECKED_AT_INVALID", selected=len(rows))
        sql = _statements(rows, outcomes, timestamp)
        descriptor, name = tempfile.mkstemp(prefix="data-lab-affiliate-revalidation-", suffix=".sql")
        temporary_path = Path(name)
        write_succeeded = False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(sql)
            process = _wrangler(
                ["d1", "execute", DATABASE_NAME, "--remote", "--json", "--file", str(temporary_path)],
                runner,
            )
            write_succeeded = _write_succeeded(process)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        if not write_succeeded:
            return _result("FAILED_SAFE", mode, "D1_WRITE_FAILED", selected=len(rows),
                           valid=sum(value[0] == "VALID" for value in outcomes),
                           disabled=sum(value[0] != "VALID" for value in outcomes),
                           temporary_sql_deleted=not temporary_path.exists())
        return _result(
            "COMPLETED", mode, "BOUNDED_REVALIDATION_COMPLETED", selected=len(rows),
            valid=sum(value[0] == "VALID" for value in outcomes),
            disabled=sum(value[0] != "VALID" for value in outcomes),
            database_write_performed=True, temporary_sql_deleted=True,
        )
    except Exception:
        deleted = temporary_path is None or not temporary_path.exists()
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
                deleted = True
            except OSError:
                deleted = False
        return _result("FAILED_SAFE", mode, "LOCAL_REVALIDATION_FAILED",
                       temporary_sql_deleted=deleted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bounded local affiliate revalidation cycle.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    result = run_cycle(execute=args.execute, confirmed=args.confirm == CONFIRMATION)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status in {"READY", "COMPLETED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
