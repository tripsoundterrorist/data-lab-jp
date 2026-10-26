"""Offline five-item handoff prototype. No IO, acquisition or trusted provenance.

Returned JSON is unauthenticated, unencrypted review material, never a release
receipt. Existing decoder results can be caller-created; structural checks do
not establish that an API request happened. No raw payload or affiliate URL is
accepted by this interface. Runtime and publication integration are deliberately absent.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re

import revenue_mvp_fixed_scope_acquisition_plan as planner
import revenue_mvp_fixed_scope_response_review as decoder
from revenue_mvp_fixed_scope_refresh_review import Observation, ScopeParser, image_valid


def build(source, expected_source_sha256, database_sha256, decoded_results, *,
          batch_index, evaluated_at):
    receipt = dict(status="BLOCKED", reason_code="INPUT_INVALID", record_count=0,
                   api_calls=0, database_write_performed=False,
                   output_written=False, publication_allowed=False,
                   trusted_acquisition_confirmed=False)

    def stop(reason):
        return dict(receipt, reason_code=reason), None

    try:
        if (type(source) is not bytes or type(expected_source_sha256) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256)
                or sha256(source).hexdigest() != expected_source_sha256
                or type(database_sha256) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", database_sha256)):
            return stop("INPUT_BINDING_INVALID")
        if (type(batch_index) is not int or not 0 <= batch_index < 20
                or type(evaluated_at) is not datetime or evaluated_at.tzinfo is None
                or evaluated_at.utcoffset() is None):
            return stop("BATCH_OR_TIME_INVALID")
        plan = planner.build(source, expected_source_sha256)
        if plan.status != "OFFLINE_PLAN_READY":
            return stop("FIXED_SCOPE_INVALID")
        if type(decoded_results) is not tuple or len(decoded_results) != 5:
            return stop("EXACT_FIVE_REQUIRED")
        targets = set(plan.batches[batch_index])
        parser = ScopeParser()
        parser.feed(source.decode("utf-8"))
        parser.close()
        published_times = {
            card["ids"][0]: datetime.fromisoformat(
                card["times"][0].strip().replace("Z", "+00:00")
            ).astimezone(timezone.utc) for card in parser.cards
        }
        now = evaluated_at.astimezone(timezone.utc)
        records = []
        seen = set()
        for result in decoded_results:
            if (type(result) is not decoder.DecodeResult
                    or result.status != "STRUCTURAL_OBSERVATION_READY"
                    or type(result.price_is_lower_bound) is not bool
                    or type(result.observation) is not Observation):
                return stop("DECODED_OBSERVATION_INVALID")
            row = result.observation
            if type(row.public_id) is not str or row.public_id not in targets or row.public_id in seen:
                return stop("SCOPE_CHANGED_OR_DUPLICATED")
            if (row.outcome != "VALID" or type(row.price) is not int
                    or not 0 <= row.price <= 999999999999 or not image_valid(row.image_url)):
                return stop("FIELD_INVALID")
            times = (row.observed_at, row.price_observed_at,
                     row.image_observed_at, row.lifecycle_observed_at)
            if any(type(t) is not datetime or t.tzinfo is None or t.utcoffset() is None for t in times):
                return stop("OBSERVATION_TIME_INVALID")
            stamp = row.observed_at.astimezone(timezone.utc)
            if any(t.astimezone(timezone.utc) != stamp for t in times):
                return stop("FIELD_PROVENANCE_MISMATCH")
            if not timedelta(0) <= now - stamp <= timedelta(hours=24):
                return stop("OBSERVATION_STALE_OR_FUTURE")
            if stamp <= published_times[row.public_id]:
                return stop("OBSERVATION_NOT_NEWER_THAN_PUBLISHED")
            seen.add(row.public_id)
            records.append(dict(public_id=row.public_id, price=row.price,
                                price_is_lower_bound=result.price_is_lower_bound,
                                image_url=row.image_url, observed_at=stamp.isoformat()))
        if seen != targets:
            return stop("EXACT_FIVE_REQUIRED")
        payload = dict(version="OFFLINE_PROTOTYPE_1", source_sha256=expected_source_sha256,
                       database_sha256=database_sha256, batch_index=batch_index,
                       trusted_acquisition_confirmed=False,
                       records=sorted(records, key=lambda row: row["public_id"]))
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        return dict(receipt, status="OFFLINE_HANDOFF_STRUCTURALLY_READY",
                    reason_code="TRUSTED_CAPTURE_AND_PROTECTED_STORAGE_REQUIRED",
                    record_count=5, payload_sha256=sha256(data).hexdigest()), data
    except (TypeError, ValueError, AttributeError, OverflowError):
        return stop("INPUT_INVALID")
