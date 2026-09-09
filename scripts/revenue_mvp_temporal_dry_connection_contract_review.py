"""Static review of the isolated adapter-to-harness connection contract."""

from dataclasses import asdict, dataclass
import inspect
import json
from typing import Any

import revenue_mvp_temporal_series_connection_readiness as readiness
import temporal_probe_series_connection_harness as harness
import temporal_probe_series_integration_adapter as adapter

VERSION = "0.2"
CONTRACT_CHANGE_REQUIRED = "VALIDATED_STATE_BUNDLE_CONTRACT_REQUIRED"
CONTRACT_READY = "VALIDATED_STATE_BUNDLE_CONTRACT_READY"
FAIL_CLOSED = "FAIL_CLOSED"
NEXT_GATE = "CONNECT_ISOLATED_BUNDLE_TO_DRY_HARNESS"


@dataclass(frozen=True)
class DryConnectionContractReview:
    version: str
    status: str
    readiness_evidence_verified: bool
    adapter_accepts_sanitized_payloads: bool
    harness_accepts_validated_states: bool
    public_validated_state_bundle_available: bool
    private_validator_dependency_allowed: bool
    duplicate_payload_validation_allowed: bool
    active_connection_authorized: bool
    state_write_authorized: bool
    next_gate: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def review_dry_connection_contract() -> DryConnectionContractReview:
    """Detect the missing public handoff without executing either contract."""
    try:
        ready = readiness.assess_connection_readiness()
        adapter_parameters = inspect.signature(
            adapter.run_series_integration_dry_run
        ).parameters
        harness_parameters = inspect.signature(
            harness.run_dry_connection_harness
        ).parameters
        readiness_verified = (
            ready.status == readiness.REVIEW_READY
            and ready.evidence_complete
            and not ready.connection_authorized
        )
        adapter_accepts_payloads = {
            "series_id", "captured_at", "as_of", "payloads",
            "documents_by_population", "history_counts",
        }.issubset(adapter_parameters)
        harness_accepts_states = {
            "current_states", "documents_by_population", "history_counts",
            "as_of",
        }.issubset(harness_parameters)
        public_bundle = callable(getattr(
            adapter, "build_validated_series_state_bundle", None
        ))
        valid_boundary = (
            readiness_verified and adapter_accepts_payloads
            and harness_accepts_states
        )
        if not valid_boundary:
            return DryConnectionContractReview(
                VERSION, FAIL_CLOSED, readiness_verified,
                adapter_accepts_payloads, harness_accepts_states,
                public_bundle, False, False, False, False, None,
                ("DRY_CONNECTION_CONTRACT_CHANGED_OR_INCOMPLETE",),
            )
        if not public_bundle:
            return DryConnectionContractReview(
                VERSION, CONTRACT_CHANGE_REQUIRED, True, True, True,
                False, False, False, False, False, None,
                ("PUBLIC_VALIDATED_STATE_HANDOFF_MISSING",),
            )
        return DryConnectionContractReview(
            VERSION, CONTRACT_READY, True, True, True,
            True, False, False, False, False, NEXT_GATE,
            ("PUBLIC_VALIDATED_STATE_HANDOFF_READY",
             "SINGLE_VALIDATION_BOUNDARY_REQUIRED"),
        )
    except Exception:
        return DryConnectionContractReview(
            VERSION, FAIL_CLOSED, False, False, False, False,
            False, False, False, False, None,
            ("DRY_CONNECTION_CONTRACT_REVIEW_ERROR",),
        )


def main() -> int:
    result = review_dry_connection_contract()
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status == CONTRACT_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
