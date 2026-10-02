"""Read-only aggregate progress plan after bounded expansion validation batches."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import affiliate_d1_incremental_reconciliation as reconciliation
import revenue_mvp_expansion_d1_delta as delta_builder


VERSION = "0.1"
READY = "ACTIVATION_PROGRESS_REVIEWED"
BLOCKED = "ACTIVATION_PROGRESS_BLOCKED"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "runtime-candidates/affiliate-item-lookup-schema.sql"
BEFORE = ROOT / "runtime/private/affiliate-runtime-prewrite-20261001.sql"
CURRENT = ROOT / "runtime/private/affiliate-runtime-post-initial-batch-000-20261001.sql"
CANDIDATE = ROOT / "runtime/private/affiliate-item-lookup-expansion.sql"
FINAL_COVERAGE = ROOT / "runtime/evidence/revenue-mvp-expansion-final-runtime-coverage-20261002.json"
EXPECTED_BEFORE_SHA256 = "59c6b2d4dfb3b37467c9ae3f0cc453c8db942537af81771a29c47b0d4a460801"
EXPECTED_CURRENT_SHA256 = "9220bce210aa3cb968949c986451ea9706bfb4c9f030096a8f01a1cb31ca96d1"
EXPECTED_CANDIDATE_SHA256 = "d77105c1d0d81e2b79135b42c5163f1d722b55ad9806324b15ce2f3da1390434"
BATCH_SIZE = 5
INERT = ("PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION", "PENDING", 0)
ACTIVE = ("CONDITIONALLY_APPROVED", "RESOLVED", "PASS", 1)
RETRY = ("CONDITIONALLY_APPROVED", "RESOLVED", "PENDING", 0)


@dataclass(frozen=True)
class ActivationProgress:
    version: str
    status: str
    candidate_count: int
    initial_completed_count: int
    initial_remaining_count: int
    retry_waiting_count: int
    active_count: int
    legacy_pending_review_count: int
    redirect_target_count: int
    runtime_redirect_count: int
    next_initial_batch_size: int
    remaining_initial_batch_count: int
    api_request_performed: bool
    d1_write_performed: bool
    live_execution_allowed: bool
    explicit_live_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> ActivationProgress:
    return ActivationProgress(
        VERSION, BLOCKED, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        False, False, False, True, (reason,),
    )


def assess(before: bytes, current: bytes, candidate: bytes, schema: bytes) -> ActivationProgress:
    connections: list[sqlite3.Connection] = []
    try:
        candidate_rows = reconciliation._parse_candidate(candidate)
        if len(candidate_rows) != 300 or len(set(candidate_rows)) != 300:
            return _blocked("CANDIDATE_SCOPE_INVALID")
        states = []
        for payload in (before, current):
            connection = sqlite3.connect(":memory:")
            connections.append(connection)
            delta_builder.load_remote_snapshot(connection, schema, payload)
            states.append({row[0]: row for row in connection.execute(
                """SELECT public_id,content_id,rights_status,lifecycle_status,
                          verification_status,affiliate_enabled
                   FROM affiliate_item_lookup"""
            )})
        before_rows, current_rows = states
        candidate_map = dict(candidate_rows)
        if any(
            public_id not in current_rows
            or current_rows[public_id][1] != content_id
            for public_id, content_id in candidate_rows
        ):
            return _blocked("CURRENT_CANDIDATE_MAPPING_INVALID")
        new_ids = set(candidate_map) - set(before_rows)
        if len(new_ids) != 178:
            return _blocked("INITIAL_SCOPE_INVALID")
        old_ids = set(candidate_map) - new_ids
        new_states = [current_rows[value][2:] for value in new_ids]
        old_states = [current_rows[value][2:] for value in old_ids]
        initial_remaining = sum(state == INERT for state in new_states)
        initial_completed = sum(state == ACTIVE for state in new_states)
        retry = sum(state == RETRY for state in new_states + old_states)
        active = sum(state == ACTIVE for state in new_states + old_states)
        legacy = sum(state == INERT for state in old_states)
        if initial_remaining + initial_completed + sum(
            state == RETRY for state in new_states
        ) != len(new_states):
            return _blocked("NEW_SCOPE_STATE_INVALID")
        if sum(state in {ACTIVE, RETRY, INERT} for state in old_states) != len(old_states):
            return _blocked("PREEXISTING_SCOPE_STATE_INVALID")
        current_connection = connections[1]
        placeholders = ",".join("?" for _ in candidate_rows)
        ids = tuple(candidate_map)
        redirects = current_connection.execute(
            f"SELECT count(*) FROM affiliate_redirect_target WHERE public_id IN ({placeholders})",
            ids,
        ).fetchone()[0]
        runtime = current_connection.execute(
            f"SELECT count(*) FROM affiliate_runtime_redirect_target WHERE public_id IN ({placeholders})",
            ids,
        ).fetchone()[0]
        return ActivationProgress(
            VERSION, READY, 300, initial_completed, initial_remaining, retry,
            active, legacy, redirects, runtime, min(BATCH_SIZE, initial_remaining),
            (initial_remaining + BATCH_SIZE - 1) // BATCH_SIZE,
            False, False, False, True,
            (
                "READ_ONLY_AGGREGATE_PROGRESS",
                "INITIAL_AND_RETRY_QUEUES_SEPARATED",
                "EXPLICIT_LIVE_APPROVAL_REQUIRED",
            ),
        )
    except (sqlite3.Error, ValueError, TypeError):
        return _blocked("ACTIVATION_PROGRESS_FAILED")
    finally:
        for connection in connections:
            connection.close()


def current_progress() -> ActivationProgress:
    try:
        value = json.loads(FINAL_COVERAGE.read_text(encoding="utf-8"))
        valid = (
            type(value) is dict
            and value.get("version") == VERSION
            and value.get("status") == "FINAL_RUNTIME_COVERAGE_VERIFIED"
            and value.get("target_item_count") == 300
            and value.get("candidate_lookup_ready_count") == 300
            and value.get("candidate_redirect_ready_count") == 300
            and value.get("candidate_runtime_revalidation_ready_count") == 300
            and value.get("initial_remaining_count") == 0
            and value.get("retry_waiting_count") == 0
            and value.get("legacy_pending_review_count") == 0
            and value.get("identifiers_exposed") is False
            and value.get("publication_allowed") is False
            and value.get("production_write_allowed") is False
            and value.get("deployment_allowed") is False
            and type(value.get("postwrite_d1_snapshot_sha256")) is str
            and len(value["postwrite_d1_snapshot_sha256"]) == 64
            and all(character in "0123456789abcdef" for character in value["postwrite_d1_snapshot_sha256"])
        )
        if not valid:
            return _blocked("FINAL_COVERAGE_EVIDENCE_INVALID")
        return ActivationProgress(
            VERSION, READY, 300, 178, 0, 0, 300, 0, 300, 300, 0, 0,
            False, False, False, True,
            (
                "READ_ONLY_AGGREGATE_PROGRESS",
                "ALL_ACTIVATION_QUEUES_EMPTY",
                "PUBLICATION_REVIEW_SEPARATE",
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return _blocked("FINAL_COVERAGE_EVIDENCE_UNAVAILABLE")


def main() -> int:
    result = current_progress()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
