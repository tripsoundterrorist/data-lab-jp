"""Build an identifier-free, non-executing activation batch plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import sqlite3
from typing import Any

import affiliate_d1_incremental_reconciliation as reconciliation
import revenue_mvp_expansion_d1_delta as delta_builder


VERSION = "0.1"
READY = "ACTIVATION_BATCH_PLAN_READY"
BLOCKED = "BLOCKED"
BATCH_SIZE = 5


@dataclass(frozen=True)
class BatchPlan:
    version: str
    status: str
    candidate_count: int
    new_initial_validation_count: int
    upstream_retry_count: int
    currently_active_count: int
    legacy_pending_review_count: int
    batch_size: int
    initial_batch_count: int
    retry_batch_count: int
    retry_attempt_limit: int
    wait_seconds_upper_bound: int
    api_request_performed: bool
    d1_write_performed: bool
    activation_allowed: bool
    explicit_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> BatchPlan:
    return BatchPlan(
        VERSION, BLOCKED, 0, 0, 0, 0, 0, BATCH_SIZE, 0, 0, 1, 300,
        False, False, False, True, (reason,),
    )


def assess(
    before: bytes, after: bytes, candidate: bytes, schema: bytes, *,
    expected_new_count: int = 178,
) -> BatchPlan:
    connections: list[sqlite3.Connection] = []
    try:
        candidate_rows = reconciliation._parse_candidate(candidate)
        if len(candidate_rows) != 300:
            return _blocked("CANDIDATE_COUNT_INVALID")
        states = []
        for payload in (before, after):
            connection = sqlite3.connect(":memory:")
            connections.append(connection)
            delta_builder.load_remote_snapshot(connection, schema, payload)
            states.append({row[0]: row for row in connection.execute(
                """SELECT public_id,content_id,rights_status,lifecycle_status,
                          verification_status,affiliate_enabled
                   FROM affiliate_item_lookup"""
            )})
        before_rows, after_rows = states
        candidate_ids = {public_id for public_id, _ in candidate_rows}
        new_ids = candidate_ids - set(before_rows)
        if (
            type(expected_new_count) is not int or expected_new_count <= 0
            or len(new_ids) != expected_new_count
            or not candidate_ids.issubset(after_rows)
        ):
            return _blocked("SNAPSHOT_SCOPE_INVALID")
        new_safe = all(
            after_rows[value][2:] == (
                "PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION", "PENDING", 0
            ) for value in new_ids
        )
        if not new_safe:
            return _blocked("NEW_ROWS_NOT_INERT")
        old = [after_rows[value] for value in candidate_ids - new_ids]
        active = sum(row[2:] == ("CONDITIONALLY_APPROVED", "RESOLVED", "PASS", 1) for row in old)
        retry = sum(row[2:] == ("CONDITIONALLY_APPROVED", "RESOLVED", "PENDING", 0) for row in old)
        legacy = sum(row[2:] == (
            "PENDING_SEPARATE_POLICY", "PENDING_OFFICIAL_CONFIRMATION", "PENDING", 0
        ) for row in old)
        if active + retry + legacy != len(old):
            return _blocked("PREEXISTING_STATE_REVIEW_REQUIRED")
        return BatchPlan(
            VERSION, READY, 300, len(new_ids), retry, active, legacy, BATCH_SIZE,
            (len(new_ids) + BATCH_SIZE - 1) // BATCH_SIZE,
            (retry + BATCH_SIZE - 1) // BATCH_SIZE,
            1, 300, False, False, False, True,
            (
                "NEW_AND_RETRY_QUEUES_SEPARATED", "FIVE_ITEM_BATCH_MAXIMUM",
                "NO_AUTOMATIC_RETRY", "LEGACY_PENDING_REQUIRES_SEPARATE_REVIEW",
                "EXPLICIT_LIVE_APPROVAL_REQUIRED",
            ),
        )
    except Exception:
        return _blocked("BATCH_PLAN_FAILED")
    finally:
        for connection in connections:
            connection.close()


__all__ = ["BatchPlan", "assess"]
