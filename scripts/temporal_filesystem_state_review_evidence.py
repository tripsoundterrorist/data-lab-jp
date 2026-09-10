"""Build fixed, read-only evidence for the filesystem-state review Gate."""

from __future__ import annotations

from dataclasses import fields
import inspect
import json

import temporal_filesystem_state_connection_review as review
import temporal_probe_series_integration_adapter as adapter
import temporal_probe_series_state_store_candidate as store
import temporal_probe_validated_bundle_dry_connection as connection


EXPECTED_BUNDLE_FIELDS = (
    "version", "success", "validated_population_count", "states",
    "active_pipeline_connected", "api_request_authorized",
    "state_write_authorized", "reason_codes",
)
EXPECTED_PLAN_FIELDS = (
    "version", "status", "success", "filename", "document_sha256",
    "document_bytes", "series_aware_identity", "filesystem_access_performed",
    "state_write_authorized", "reason_codes",
)
NEXT_MINIMUM_GATE = "DEFINE_ISOLATED_FILESYSTEM_PERSISTENCE_READBACK_CONTRACT"


def collect_filesystem_state_review_evidence() -> review.FilesystemStateConnectionEvidence:
    """Inspect public symbols only; never execute a target contract."""

    try:
        bundle_fields = tuple(field.name for field in fields(
            adapter.ValidatedSeriesStateBundle
        ))
        plan_fields = tuple(field.name for field in fields(store.SeriesStateWritePlan))
        plan_parameters = tuple(inspect.signature(store.plan_series_state_write).parameters)
        connection_parameters = tuple(inspect.signature(
            connection.connect_validated_bundle_to_dry_harness
        ).parameters)

        prerequisites = (
            store.STORE_CANDIDATE_VERSION == "0.2-candidate"
            and bundle_fields == EXPECTED_BUNDLE_FIELDS
            and plan_fields == EXPECTED_PLAN_FIELDS
            and plan_parameters == ("state", "as_of")
            and connection_parameters
            == ("bundle", "documents_by_population", "history_counts", "as_of")
        )
        secret_pii = (
            "series_id" not in plan_fields
            and "content_id" not in plan_fields
            and "payload" not in plan_fields
            and store.MAX_STATE_BYTES == 1024 * 1024
            and store.STATE_FILENAME.pattern.startswith("(?:rank|review)-")
            and "series-[a-f0-9]{16}" in store.STATE_FILENAME.pattern
        )
        publication_separated = (
            "publication" not in plan_fields
            and "affiliate" not in plan_fields
            and "route" not in plan_fields
            and "deploy" not in plan_fields
        )
        explicit_approval_point = (
            review.SELECTED_TARGET == "FILESYSTEM_BACKED_STATE"
            and review.REVIEW_READY_FOR_EXPLICIT_APPROVAL
            == "REVIEW_READY_FOR_EXPLICIT_APPROVAL"
        )
        return review.FilesystemStateConnectionEvidence(
            version=review.VERSION,
            selected_target=review.SELECTED_TARGET,
            prerequisites_verified=prerequisites,
            trust_boundary_verified=False,
            rollback_recovery_verified=False,
            secret_pii_controls_verified=secret_pii,
            idempotency_verified=False,
            rate_cost_bounds_verified=False,
            publication_compliance_separation_verified=publication_separated,
            explicit_approval_point_defined=explicit_approval_point,
            explicit_approval_granted=False,
        )
    except Exception:
        return review.FilesystemStateConnectionEvidence(
            review.VERSION, review.SELECTED_TARGET,
            False, False, False, False, False, False, False, False, False,
        )


def assess_current_filesystem_state_review() -> review.FilesystemStateConnectionReview:
    return review.review_filesystem_state_connection(
        collect_filesystem_state_review_evidence()
    )


def main() -> int:
    result = assess_current_filesystem_state_review()
    payload = result.to_dict()
    payload["next_minimum_gate"] = NEXT_MINIMUM_GATE
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.status == review.REVIEW_READY_FOR_EXPLICIT_APPROVAL else 2


if __name__ == "__main__":
    raise SystemExit(main())
