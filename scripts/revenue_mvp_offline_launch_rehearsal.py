"""Pure offline launch rehearsal for lifecycle-filtered Public Data artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

import publication_artifact_validator as validator
import revenue_mvp_offline_artifact_integration as integration
import revenue_mvp_official_lifecycle_policy as lifecycle_policy
import revenue_mvp_offline_lifecycle_filter as lifecycle_filter
from product_verification import Observation, VerificationObservation


VERSION = "0.1-candidate"
REHEARSAL_COMPLETE = "OFFLINE_REHEARSAL_COMPLETE"
FAIL_CLOSED = "OFFLINE_REHEARSAL_FAIL_CLOSED"
REQUIRED_EXCLUSION_SCENARIOS = frozenset({
    "NON_TARGET", "AFFILIATE_URL_MISSING", "AFFILIATE_URL_UNKNOWN",
    "API_ERROR", "RATE_LIMITED", "STALE",
})
_EXPECTED_SCENARIOS = {
    "NON_TARGET": (
        Observation.API_ITEM_NOT_RETURNED,
        lifecycle_policy.EligibilityState.EXCLUDED,
        "API_UNAVAILABLE_EXCLUDED_FROM_PUBLIC_SITE",
    ),
    "AFFILIATE_URL_MISSING": (
        Observation.API_ITEM_VISIBLE,
        lifecycle_policy.EligibilityState.EXCLUDED,
        "AFFILIATE_URL_ABSENT_OR_UNKNOWN",
    ),
    "AFFILIATE_URL_UNKNOWN": (
        Observation.API_ITEM_VISIBLE,
        lifecycle_policy.EligibilityState.EXCLUDED,
        "AFFILIATE_URL_ABSENT_OR_UNKNOWN",
    ),
    "API_ERROR": (
        Observation.API_ERROR,
        lifecycle_policy.EligibilityState.TEMPORARILY_BLOCKED,
        "API_ERROR_REQUIRES_BOUNDED_WAIT",
    ),
    "RATE_LIMITED": (
        Observation.API_RATE_LIMITED,
        lifecycle_policy.EligibilityState.TEMPORARILY_BLOCKED,
        "RATE_LIMIT_MUST_BE_RESPECTED",
    ),
    "STALE": (
        Observation.API_ITEM_VISIBLE,
        lifecycle_policy.EligibilityState.CANDIDATE,
        "API_VISIBLE_WITH_AFFILIATE_URL",
    ),
}


@dataclass(frozen=True)
class ExclusionScenario:
    name: str
    observation: VerificationObservation
    evidence_by_public_id: Mapping[str, integration.OfflineArtifactItemEvidence]


@dataclass(frozen=True)
class ForbiddenScenario:
    name: str
    files: Mapping[str, bytes]


@dataclass(frozen=True)
class OfflineLaunchRehearsalReport:
    version: str
    status: str
    candidate_index_detail_consistent: bool
    candidate_cta_disabled: bool
    exclusions_verified: int
    exclusions_required: int
    manifest_count_digest_verified: bool
    forbidden_inputs_fail_closed: bool
    rollback_deterministic: bool
    rollback_source_sha256: str | None
    production_publication_allowed: bool
    publication_gate_change_allowed: bool
    external_io_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(code: str) -> OfflineLaunchRehearsalReport:
    return OfflineLaunchRehearsalReport(
        VERSION, FAIL_CLOSED, False, False, 0,
        len(REQUIRED_EXCLUSION_SCENARIOS), False, False, False, None,
        False, False, False, (code,),
    )


def _snapshot_sha256(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path])
    return digest.hexdigest()


def restore_local_validation_snapshot(snapshot: Any) -> dict[str, bytes]:
    """Return a validated byte-for-byte copy; never writes the snapshot."""

    if not isinstance(snapshot, Mapping):
        return {}
    restored = {
        path: bytes(content)
        for path, content in snapshot.items()
        if type(path) is str and type(content) is bytes
    }
    if len(restored) != len(snapshot):
        return {}
    result = validator.validate_artifacts(restored)
    if result.artifact_validation != validator.PASS:
        return {}
    try:
        manifest = json.loads(restored["manifest.json"])
    except (KeyError, UnicodeError, json.JSONDecodeError):
        return {}
    if manifest.get("publication_status") != "local_validation_only":
        return {}
    return restored


def run_offline_launch_rehearsal(
    source_files: Any,
    candidate_evidence: Any,
    exclusion_scenarios: Any,
    forbidden_scenarios: Any,
) -> OfflineLaunchRehearsalReport:
    """Exercise candidate, exclusion, rejection, smoke, and rollback paths."""

    try:
        if (
            not isinstance(source_files, Mapping)
            or not isinstance(candidate_evidence, Mapping)
            or type(exclusion_scenarios) is not tuple
            or type(forbidden_scenarios) is not tuple
            or any(type(value) is not ExclusionScenario for value in exclusion_scenarios)
            or any(type(value) is not ForbiddenScenario for value in forbidden_scenarios)
            or not forbidden_scenarios
        ):
            return _failed("REHEARSAL_INPUT_INVALID")
        names = tuple(value.name for value in exclusion_scenarios)
        if len(names) != len(set(names)) or set(names) != REQUIRED_EXCLUSION_SCENARIOS:
            return _failed("EXCLUSION_SCENARIOS_INCOMPLETE")

        candidate = integration.filter_offline_publication_artifacts(
            source_files, candidate_evidence
        )
        if (
            candidate.status != integration.COMPLETE
            or candidate.input_item_count != 1
            or candidate.included_item_count != 1
            or candidate.excluded_item_count != 0
            or candidate.production_publication_allowed is not False
            or candidate.publication_gate_change_allowed is not False
            or candidate.external_io_performed is not False
        ):
            return _failed("CANDIDATE_SMOKE_FAILED")
        documents = {
            path: json.loads(content.decode("utf-8"))
            for path, content in candidate.files.items()
        }
        index_items = documents["index.json"]["items"]
        detail_paths = tuple(path for path in documents if path.startswith("items/"))
        consistent = len(index_items) == 1 and len(detail_paths) == 1
        detail_item = documents[detail_paths[0]]["item"] if consistent else {}
        cta_disabled = detail_item.get("affiliate_cta_eligible") is False
        manifest = documents["manifest.json"]
        digest_verified = (
            manifest.get("item_count") == 1
            and manifest.get("index_sha256")
            == hashlib.sha256(candidate.files["index.json"]).hexdigest()
            and validator.validate_artifacts(candidate.files).artifact_validation
            == validator.PASS
        )
        if not consistent or not cta_disabled or not digest_verified:
            return _failed("CANDIDATE_ARTIFACT_INVALID")

        exclusions = 0
        for scenario in exclusion_scenarios:
            expected_observation, expected_state, expected_reason = (
                _EXPECTED_SCENARIOS[scenario.name]
            )
            decision = lifecycle_policy.evaluate_official_lifecycle_policy(
                scenario.observation
            )
            evidence_values = tuple(scenario.evidence_by_public_id.values())
            if (
                type(scenario.observation) is not VerificationObservation
                or scenario.observation.observation is not expected_observation
                or decision.state is not expected_state
                or expected_reason not in decision.reason_codes
                or len(evidence_values) != 1
            ):
                return _failed("EXCLUSION_SCENARIO_MISMATCH")
            lifecycle_result = evidence_values[0].lifecycle
            expected_filter_reason = (
                "FRESHNESS_NOT_CONFIRMED"
                if scenario.name == "STALE" else "LIFECYCLE_NOT_ELIGIBLE"
            )
            if (
                type(lifecycle_result)
                is not lifecycle_filter.OfflineLifecycleFilterResult
                or lifecycle_result.status != lifecycle_filter.EXCLUDED
                or expected_filter_reason not in lifecycle_result.reason_codes
                or lifecycle_result.lifecycle_state != decision.state.value
                or lifecycle_result.lifecycle_reason_codes != decision.reason_codes
            ):
                return _failed("EXCLUSION_FILTER_EVIDENCE_MISMATCH")
            if scenario.name == "AFFILIATE_URL_MISSING" and (
                scenario.observation.affiliate_link_observed is not False
            ):
                return _failed("EXCLUSION_SCENARIO_MISMATCH")
            if scenario.name == "AFFILIATE_URL_UNKNOWN" and (
                scenario.observation.affiliate_link_observed is not None
            ):
                return _failed("EXCLUSION_SCENARIO_MISMATCH")
            result = integration.filter_offline_publication_artifacts(
                source_files, scenario.evidence_by_public_id
            )
            if (
                result.status != integration.COMPLETE
                or result.included_item_count != 0
                or result.excluded_item_count != 1
                or any(path.startswith("items/") for path in result.files)
                or json.loads(result.files["index.json"])["items"] != []
            ):
                return _failed("EXCLUSION_SMOKE_FAILED")
            exclusions += 1

        for scenario in forbidden_scenarios:
            result = integration.filter_offline_publication_artifacts(
                scenario.files, candidate_evidence
            )
            if result.status != integration.FAIL_CLOSED or result.files:
                return _failed("FORBIDDEN_INPUT_NOT_BLOCKED")

        first_restore = restore_local_validation_snapshot(source_files)
        second_restore = restore_local_validation_snapshot(source_files)
        rollback_sha = _snapshot_sha256(first_restore) if first_restore else None
        rollback = (
            bool(first_restore)
            and first_restore == source_files
            and second_restore == first_restore
            and _snapshot_sha256(second_restore) == rollback_sha
        )
        if not rollback:
            return _failed("ROLLBACK_RESTORE_FAILED")
        return OfflineLaunchRehearsalReport(
            VERSION, REHEARSAL_COMPLETE, True, True, exclusions,
            len(REQUIRED_EXCLUSION_SCENARIOS), True, True, True, rollback_sha,
            False, False, False,
            ("OFFLINE_SMOKE_COMPLETE", "ROLLBACK_VERIFIED", "PRODUCTION_REMAINS_CLOSED"),
        )
    except Exception:
        return _failed("OFFLINE_REHEARSAL_INTERNAL_ERROR")


__all__ = [
    "ExclusionScenario", "FAIL_CLOSED", "ForbiddenScenario",
    "OfflineLaunchRehearsalReport", "REHEARSAL_COMPLETE",
    "REQUIRED_EXCLUSION_SCENARIOS", "VERSION",
    "restore_local_validation_snapshot", "run_offline_launch_rehearsal",
]
