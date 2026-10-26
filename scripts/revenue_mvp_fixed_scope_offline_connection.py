"""Synthetic/offline response-to-handoff rehearsal. No transport or storage.

Caller-supplied responses never prove acquisition. This module deliberately
cannot issue process-owned acquisition evidence or invoke capture/archive APIs.
"""
from dataclasses import dataclass, field
from datetime import datetime

import revenue_mvp_fixed_scope_acquisition_plan as planner
import revenue_mvp_fixed_scope_response_review as decoder
import revenue_mvp_fixed_scope_handoff as handoff
from revenue_mvp_lifecycle_receipt import public_item_id


@dataclass(frozen=True)
class OfflineResponse:
    public_id: str
    content_id: str = field(repr=False)
    payload: object = field(repr=False)
    http_status: int
    observed_at: datetime


def rehearse(source, source_sha256, database_sha256, responses, *, batch_index, evaluated_at):
    summary = dict(status="BLOCKED", reason_code="INPUT_INVALID", decoded_count=0,
                   api_calls=0, output_written=False, database_write_performed=False,
                   publication_allowed=False, trusted_acquisition_confirmed=False)

    def stop(reason):
        return dict(summary, reason_code=reason), None

    try:
        if type(batch_index) is not int or not 0 <= batch_index < 20:
            return stop("BATCH_INVALID")
        plan = planner.build(source, source_sha256)
        if plan.status != "OFFLINE_PLAN_READY":
            return stop("SOURCE_BINDING_OR_SCOPE_INVALID")
        if type(responses) is not tuple or len(responses) != 5:
            return stop("EXACT_FIVE_REQUIRED")
        expected = set(plan.batches[batch_index])
        seen = set()
        for response in responses:
            if (type(response) is not OfflineResponse or type(response.public_id) is not str
                    or response.public_id not in expected or response.public_id in seen
                    or type(response.content_id) is not str
                    or not decoder.CID.fullmatch(response.content_id)
                    or public_item_id("FANZA", "digital", "videoa", response.content_id) != response.public_id):
                return stop("IDENTITY_OR_SCOPE_INVALID")
            seen.add(response.public_id)
        results = []
        for response in responses:
            result = decoder.decode(target_public_id=response.public_id,
                resolved_content_id=response.content_id, payload=response.payload,
                http_status=response.http_status, observed_at=response.observed_at,
                evaluated_at=evaluated_at)
            if result.status != "STRUCTURAL_OBSERVATION_READY":
                return stop(result.reason_code)
            results.append(result)
            summary["decoded_count"] += 1
        receipt, data = handoff.build(source, source_sha256, database_sha256,
            tuple(results), batch_index=batch_index, evaluated_at=evaluated_at)
        if data is None:
            return stop(receipt["reason_code"])
        return dict(summary, status="OFFLINE_CONNECTION_REHEARSED",
                    reason_code="NOT_ACQUISITION_EVIDENCE_OR_SAVE_PERMISSION",
                    payload_sha256=receipt["payload_sha256"]), data
    except (ValueError, TypeError, AttributeError, OverflowError):
        return stop("INPUT_INVALID")
