"""Explicit remaining-90 read-only run; fixed batches 2..19, no persistence."""
import revenue_mvp_fixed_scope_first_five as batch

CONFIRMATION = "READ_ONLY_FIXED_SCOPE_REMAINING_NINETY"


def check(source, database, environment, source_digest, database_digest, *,
          execute=False, confirmation=None, checker=None, progress=None):
    result = {"status": "BLOCKED", "reason_code": "INPUT_INVALID",
              "api_calls": 0, "validated_count": 0, "completed_batches": 0,
              "lower_bound_price_count": 0, "database_write_performed": False,
              "d1_write_performed": False, "raw_payload_persisted": False,
              "publication_allowed": False, "scheduler_changed": False}
    if not batch.bound(source,database,source_digest,database_digest):
        return result
    plan = batch.planner.build(source.read_bytes(),source_digest)
    if plan.status != "OFFLINE_PLAN_READY" or len(plan.batches) != 20:
        return result
    if execute is not True:
        result.update(status="OFFLINE_REMAINING_NINETY_READY",
                      reason_code="EXPLICIT_LIVE_CONFIRMATION_REQUIRED")
        return result
    if confirmation != CONFIRMATION:
        result["reason_code"] = "LIVE_CONFIRMATION_REQUIRED"
        return result
    checker = batch.check if checker is None else checker
    for index in range(2,20):
        if not batch.bound(source,database,source_digest,database_digest):
            result["reason_code"] = "INPUT_CHANGED"
            return result
        try:
            part = checker(source,database,environment,source_digest,database_digest,
                           execute=True,confirmation=batch.batch_confirmation(index),
                           batch_index=index)
        except Exception:
            result["reason_code"] = "BATCH_EXCEPTION_STOP"
            return result
        for key in ("api_calls","validated_count","lower_bound_price_count"):
            result[key] += part[key]
        if part["status"] != "FIVE_ITEM_READ_ONLY_CHECK_COMPLETE":
            result["reason_code"] = part["reason_code"]
            return result
        if part["api_calls"] != 5 or part["validated_count"] != 5:
            result["reason_code"] = "BATCH_COUNT_INVALID"
            return result
        result["completed_batches"] += 1
        if progress is not None:
            progress({"completed_batches":result["completed_batches"],
                      "api_calls":result["api_calls"],
                      "validated_count":result["validated_count"]})
    result.update(status="REMAINING_NINETY_READ_ONLY_CHECK_COMPLETE",
                  reason_code="NO_UPDATE_OR_PUBLICATION_AUTHORIZED")
    return result
