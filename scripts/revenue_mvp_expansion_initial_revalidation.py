"""Bounded initial API revalidation for newly inserted expansion rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

import affiliate_local_lifecycle_revalidation as shared
from affiliate_runtime_dmm_connector import AffiliateRuntimeConnectorError, fetch_item_response
from affiliate_d1_sensitive_query import D1QueryClient, build_queries


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
    database_write_performed: bool | None
    temporary_sql_deleted: bool
    reason_codes: tuple[str, ...]
    provider_attempts: int = 0
    write_outcome: str = "NOT_ATTEMPTED"

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


def run(*, public_ids: tuple[str, ...], execute: bool = False, confirmed: bool = False,
        runner: Callable[..., Any] = subprocess.run, fetcher: Callable[..., Any] = fetch_item_response,
        checked_at: str | None = None, query_client: D1QueryClient | None = None) -> Result:
    mode = "LIVE" if execute else "DRY_RUN"
    selected_count = 0
    provider_attempts = 0
    stage = "SELECTION"
    try:
        if execute and confirmed is not True:
            return _result("BLOCKED", mode, "EXPLICIT_CONFIRMATION_REQUIRED")
        if (type(public_ids) is not tuple or not 1 <= len(public_ids) <= 5
                or any(type(v) is not str or shared.PUBLIC_ID.fullmatch(v) is None for v in public_ids)
                or len(set(public_ids)) != len(public_ids)):
            return _result("BLOCKED", mode, "SELECTION_INVALID")
        if execute and (not isinstance(query_client, D1QueryClient) or not query_client.ready()):
            return _result("BLOCKED", mode, "SECURE_QUERY_CLIENT_REQUIRED")
        timestamp = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if (type(timestamp) is not str or not timestamp.endswith("Z")
                or datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None):
            return _result("BLOCKED", mode, "CHECKED_AT_INVALID")
        rows = _select(public_ids, runner)
        selected_count = len(rows)
        if not execute:
            return _result("READY", mode, "INITIAL_SELECTION_VALIDATED", selected=len(rows))
        stage = "PROVIDER"
        outcomes: list[tuple[str, str | None]] = []
        for row in rows:
            try:
                provider_attempts += 1
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
        queries = build_queries(rows, outcomes, timestamp)
        stage = "D1_QUERY_WRITE"
        write = query_client.write(queries, confirmed=True)
        if write.state != "APPLIED":
            return _result("FAILED_SAFE", mode, write.reason_code, selected=len(rows),
                           provider_attempts=provider_attempts, write_outcome=write.state,
                           database_write_performed=None if write.state == "UNKNOWN" else False)
        return _result(
            "COMPLETED", mode, "QUERY_ACKNOWLEDGED_POSTCHECK_REQUIRED",
            selected=len(rows), valid=sum(x[0] == "VALID" for x in outcomes),
            unavailable=sum(x[0] == "NOT_AVAILABLE" for x in outcomes),
            unconfirmed=sum(x[0] == "UNCONFIRMED" for x in outcomes),
            database_write_performed=True,
            provider_attempts=provider_attempts, write_outcome="APPLIED",
        )
    except Exception:
        return _result("FAILED_SAFE", mode, f"INITIAL_REVALIDATION_{stage}_FAILED",
                       selected=selected_count,
                       provider_attempts=provider_attempts,
                       database_write_performed=None if stage == "D1_QUERY_WRITE" else False,
                       write_outcome="UNKNOWN" if stage == "D1_QUERY_WRITE" else "NOT_ATTEMPTED")
    finally:
        if isinstance(query_client, D1QueryClient):
            query_client.clear()


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
