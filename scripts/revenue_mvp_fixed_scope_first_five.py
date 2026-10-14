"""Manual, one explicitly confirmed fixed batch of five, read-only check.

No persistence, rendering, DB/D1 writes, retry, scheduler, or publication.
Default mode is offline. Live mode requires the explicit CLI confirmation.
Raw payload, URLs and source identifiers stay transient and are never printed.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
import urllib.request

import affiliate_runtime_dmm_connector as connector
import revenue_mvp_fixed_scope_acquisition_plan as planner
import revenue_mvp_fixed_scope_response_review as decoder

CONFIRMATION = "READ_ONLY_FIXED_SCOPE_FIRST_FIVE"
SECOND_CONFIRMATION = "READ_ONLY_FIXED_SCOPE_SECOND_FIVE"


def batch_confirmation(index):
    if type(index) is not int or not 0 <= index < 20:
        raise ValueError("BATCH_SCOPE_INVALID")
    return (CONFIRMATION if index == 0 else SECOND_CONFIRMATION if index == 1
            else f"READ_ONLY_FIXED_SCOPE_BATCH_{index:02d}")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def bound(source, database, source_digest, database_digest):
    return (not source.is_symlink() and not database.is_symlink()
            and source.is_file() and database.is_file()
            and not any(Path(str(database) + suffix).exists()
                        for suffix in ("-wal", "-shm", "-journal"))
            and digest(source) == source_digest
            and digest(database) == database_digest)


def fetch_exact(*, content_id, env_path):
    def open_exact(request, *, timeout):
        response = urllib.request.urlopen(request, timeout=timeout)
        if type(response.status) is not int or response.status != 200:
            response.close()
            raise connector.AffiliateRuntimeConnectorError("API_HTTP_STATUS_INVALID")
        return response
    return connector.fetch_item_response(content_id=content_id,
        env_path=env_path, fetcher=open_exact)


def check(source, database, environment, source_digest, database_digest, *,
          execute=False, confirmation=None, resolver=None, fetcher=None,
          clock=None, pause=None, batch_index=0):
    result = {
        "status": "BLOCKED", "reason_code": "INPUT_INVALID",
        "selected_count": 0, "api_calls": 0, "validated_count": 0,
        "lower_bound_price_count": 0, "raw_payload_persisted": False,
        "database_write_performed": False, "d1_write_performed": False,
        "publication_allowed": False, "scheduler_changed": False,
    }
    resolver = connector.resolve_content_id if resolver is None else resolver
    fetcher = fetch_exact if fetcher is None else fetcher
    clock = (lambda: datetime.now(timezone.utc)) if clock is None else clock
    pause = time.sleep if pause is None else pause

    def stop(reason):
        result["reason_code"] = reason
        return result

    try:
        if type(batch_index) is not int or not 0 <= batch_index < 20:
            return stop("BATCH_SCOPE_INVALID")
        if not bound(source, database, source_digest, database_digest):
            return stop("INPUT_BINDING_INVALID")
        plan = planner.build(source.read_bytes(), source_digest)
        if plan.status != "OFFLINE_PLAN_READY":
            return stop("FIXED_SCOPE_INVALID")
        selected = plan.batches[batch_index]
        result["batch_index"] = batch_index
        result["selected_count"] = len(selected)
        if execute is not True:
            result.update(status="OFFLINE_FIRST_FIVE_READY" if batch_index == 0
                          else "OFFLINE_SECOND_FIVE_READY" if batch_index == 1
                          else "OFFLINE_FIXED_FIVE_READY",
                          reason_code="EXPLICIT_LIVE_CONFIRMATION_REQUIRED")
            return result
        expected_confirmation = batch_confirmation(batch_index)
        if confirmation != expected_confirmation:
            return stop("LIVE_CONFIRMATION_REQUIRED")
        if len(selected) != 5 or not environment.is_file() or environment.is_symlink():
            return stop("LIVE_INPUT_INVALID")
        # Resolve every identity before any request. Hash-pin before/after lookup.
        resolved = []
        for public_id in selected:
            if not bound(source, database, source_digest, database_digest):
                return stop("INPUT_CHANGED")
            content_id = resolver(database, public_id)
            if type(content_id) is not str or not connector.CONTENT_ID.fullmatch(content_id):
                return stop("EXACT_IDENTITY_UNRESOLVED")
            if connector._public_item_id("FANZA", "digital", "videoa", content_id) != public_id:
                return stop("EXACT_IDENTITY_MISMATCH")
            resolved.append((public_id, content_id))
        if len({cid for _, cid in resolved}) != 5:
            return stop("EXACT_IDENTITY_DUPLICATED")
        for public_id, content_id in resolved:
            if not bound(source, database, source_digest, database_digest):
                return stop("INPUT_CHANGED")
            if result["api_calls"]:
                pause(1.0)
            observed_at = clock()
            result["api_calls"] += 1
            try:
                payload = fetcher(content_id=content_id, env_path=environment)
            except Exception:
                return stop("UPSTREAM_UNCONFIRMED_STOP")
            reviewed = decoder.decode(
                target_public_id=public_id, resolved_content_id=content_id,
                payload=payload, http_status=200, observed_at=observed_at,
                evaluated_at=clock())
            del payload
            if reviewed.status != "STRUCTURAL_OBSERVATION_READY":
                return stop(reviewed.reason_code)
            if not bound(source, database, source_digest, database_digest):
                return stop("INPUT_CHANGED")
            result["validated_count"] += 1
            result["lower_bound_price_count"] += int(reviewed.price_is_lower_bound is True)
            del reviewed
        result.update(status="FIVE_ITEM_READ_ONLY_CHECK_COMPLETE",
                      reason_code="NO_UPDATE_OR_PUBLICATION_AUTHORIZED")
        return result
    except Exception:
        return stop("READ_ONLY_CHECK_FAILED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--env", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--db-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--batch-index", type=int, choices=range(20), default=0)
    args = parser.parse_args()
    result = check(args.source, args.db, args.env,
                   args.source_sha256, args.db_sha256,
                   execute=args.execute, confirmation=args.confirm,
                   batch_index=args.batch_index)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
