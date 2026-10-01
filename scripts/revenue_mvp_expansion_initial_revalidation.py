"""Bounded initial API revalidation for newly inserted expansion rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping

import affiliate_local_lifecycle_revalidation as shared
from affiliate_runtime_dmm_connector import AffiliateRuntimeConnectorError, fetch_item_response


VERSION = "0.1"
CONFIRMATION = "LIVE_EXPANSION_INITIAL_REVALIDATION"


@dataclass(frozen=True)
class Result:
    version: str
    status: str
    mode: str
    selected: int
    valid: int
    unavailable: int
    unconfirmed: int
    database_write_performed: bool
    temporary_sql_deleted: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, mode: str, reason: str, **values: Any) -> Result:
    defaults = dict(selected=0, valid=0, unavailable=0, unconfirmed=0,
                    database_write_performed=False, temporary_sql_deleted=True)
    defaults.update(values)
    return Result(VERSION, status, mode, reason_codes=(reason,), **defaults)


def _select(public_ids: tuple[str, ...], runner: Callable[..., Any]) -> list[dict[str, str]]:
    quoted = ",".join(shared._quote(value) for value in public_ids)
    sql = (
        "SELECT public_id,content_id FROM affiliate_item_lookup "
        "WHERE rights_status='PENDING_SEPARATE_POLICY' "
        "AND lifecycle_status='PENDING_OFFICIAL_CONFIRMATION' "
        "AND verification_status='PENDING' AND affiliate_enabled=0 "
        f"AND public_id IN ({quoted}) ORDER BY public_id ASC LIMIT 5"
    )
    process = shared._wrangler(
        ["d1", "execute", shared.DATABASE_NAME, "--remote", "--json", "--command", sql], runner
    )
    payload = shared._json_payload(process.stdout)
    if not isinstance(payload, list) or len(payload) != 1 or payload[0].get("success") is not True:
        raise ValueError("selection response")
    rows = payload[0].get("results")
    if not isinstance(rows, list) or len(rows) != len(public_ids):
        raise ValueError("selection incomplete")
    if {row.get("public_id") for row in rows if isinstance(row, dict)} != set(public_ids):
        raise ValueError("selection mismatch")
    if any(
        set(row) != {"public_id", "content_id"}
        or shared.PUBLIC_ID.fullmatch(row["public_id"]) is None
        or shared.CONTENT_ID.fullmatch(row["content_id"]) is None
        for row in rows
    ):
        raise ValueError("selection invalid")
    return rows


def _statements(rows: list[dict[str, str]], outcomes: list[tuple[str, str | None]], checked: str) -> str:
    statements: list[str] = []
    for row, (outcome, url) in zip(rows, outcomes, strict=True):
        public_id = shared._quote(row["public_id"])
        content_id = shared._quote(row["content_id"])
        timestamp = shared._quote(checked)
        if outcome == "VALID" and url is not None:
            statements.extend((
                "INSERT INTO affiliate_redirect_target (public_id,content_id,affiliate_url,verified_at) "
                f"VALUES ({public_id},{content_id},{shared._quote(url)},{timestamp});",
                "INSERT INTO affiliate_lifecycle_revalidation_event "
                "(public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
                f"VALUES ({public_id},{timestamp},'VALID',1,'OFFICIAL_API_EXACT_MATCH');",
                "UPDATE affiliate_item_lookup SET rights_status='CONDITIONALLY_APPROVED',"
                "lifecycle_status='RESOLVED',verification_status='PASS',affiliate_enabled=1,"
                f"updated_at={timestamp} WHERE public_id={public_id} AND content_id={content_id} "
                "AND rights_status='PENDING_SEPARATE_POLICY' "
                "AND lifecycle_status='PENDING_OFFICIAL_CONFIRMATION' "
                "AND verification_status='PENDING' AND affiliate_enabled=0;",
            ))
        else:
            verification = "FAILED" if outcome == "NOT_AVAILABLE" else "PENDING"
            reason = "OFFICIAL_API_ITEM_UNAVAILABLE" if outcome == "NOT_AVAILABLE" else "LOCAL_UPSTREAM_UNCONFIRMED"
            statements.extend((
                f"UPDATE affiliate_item_lookup SET verification_status='{verification}',affiliate_enabled=0,"
                f"updated_at={timestamp} WHERE public_id={public_id} AND content_id={content_id};",
                "INSERT INTO affiliate_lifecycle_revalidation_event "
                "(public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
                f"VALUES ({public_id},{timestamp},{shared._quote(outcome)},0,{shared._quote(reason)});",
            ))
    return "\n".join(statements) + "\n"


def run(*, public_ids: tuple[str, ...], execute: bool = False, confirmed: bool = False,
        runner: Callable[..., Any] = subprocess.run, fetcher: Callable[..., Any] = fetch_item_response,
        checked_at: str | None = None) -> Result:
    mode = "LIVE" if execute else "DRY_RUN"
    temporary: Path | None = None
    selected_count = 0
    stage = "SELECTION"
    try:
        if execute and not confirmed:
            return _result("BLOCKED", mode, "EXPLICIT_CONFIRMATION_REQUIRED")
        if not 1 <= len(public_ids) <= 5 or len(set(public_ids)) != len(public_ids):
            return _result("BLOCKED", mode, "SELECTION_INVALID")
        rows = _select(public_ids, runner)
        selected_count = len(rows)
        if not execute:
            return _result("READY", mode, "INITIAL_SELECTION_VALIDATED", selected=len(rows))
        stage = "PROVIDER"
        outcomes: list[tuple[str, str | None]] = []
        for row in rows:
            try:
                payload = fetcher(content_id=row["content_id"], env_path=shared.ENV_PATH)
                result = payload.get("result") if isinstance(payload, Mapping) else None
                items = result.get("items") if isinstance(result, Mapping) else None
                if (isinstance(items, list) and len(items) == 1
                        and isinstance(items[0], Mapping)
                        and items[0].get("content_id") == row["content_id"]):
                    url = items[0].get("affiliateURL")
                    outcomes.append(("VALID", url) if shared._safe_url(url) else ("NOT_AVAILABLE", None))
                elif isinstance(items, list) and len(items) == 0:
                    outcomes.append(("NOT_AVAILABLE", None))
                else:
                    outcomes.append(("UNCONFIRMED", None))
            except (AffiliateRuntimeConnectorError, AttributeError, TypeError, ValueError):
                outcomes.append(("UNCONFIRMED", None))
        timestamp = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            return _result("BLOCKED", mode, "CHECKED_AT_INVALID", selected=selected_count)
        stage = "TEMPORARY_SQL"
        descriptor, name = tempfile.mkstemp(prefix="data-lab-expansion-initial-", suffix=".sql")
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_statements(rows, outcomes, timestamp))
        stage = "D1_WRITE"
        process = shared._wrangler(
            ["d1", "execute", shared.DATABASE_NAME, "--remote", "--json", "--file", str(temporary)], runner
        )
        success = shared._write_succeeded(process)
        temporary.unlink()
        if not success:
            return _result("FAILED_SAFE", mode, "D1_WRITE_FAILED", selected=len(rows))
        return _result(
            "COMPLETED", mode, "BOUNDED_INITIAL_REVALIDATION_COMPLETED",
            selected=len(rows), valid=sum(x[0] == "VALID" for x in outcomes),
            unavailable=sum(x[0] == "NOT_AVAILABLE" for x in outcomes),
            unconfirmed=sum(x[0] == "UNCONFIRMED" for x in outcomes),
            database_write_performed=True,
        )
    except Exception:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
        return _result("FAILED_SAFE", mode, f"INITIAL_REVALIDATION_{stage}_FAILED",
                       selected=selected_count,
                       temporary_sql_deleted=temporary is None or not temporary.exists())


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run one bounded expansion initial revalidation.")
    parser.add_argument("--selection-file", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    try:
        public_ids = shared._load_private_selection(args.selection_file)
    except (OSError, UnicodeError, ValueError):
        result = _result("BLOCKED", "LIVE" if args.execute else "DRY_RUN", "SELECTION_INVALID")
    else:
        result = run(
            public_ids=public_ids, execute=args.execute,
            confirmed=args.confirm == CONFIRMATION,
        )
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status in {"READY", "COMPLETED"} else 2


__all__ = ["CONFIRMATION", "Result", "run"]


if __name__ == "__main__":
    raise SystemExit(main())
