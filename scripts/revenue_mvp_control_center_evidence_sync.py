"""Read-only, fail-closed synchronization against a reviewed baseline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import revenue_mvp_bounded_verification_runner as bounded_runner
import revenue_mvp_lifecycle_receipt as lifecycle_receipt
import revenue_mvp_official_lifecycle_policy as lifecycle_policy
import revenue_mvp_offline_artifact_integration as artifact_integration
import revenue_mvp_offline_launch_rehearsal as launch_rehearsal
import revenue_mvp_offline_lifecycle_filter as lifecycle_filter
import revenue_mvp_reduced_surface_gate_mapping as gate_mapping


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "docs" / "policies" / "revenue-mvp-control-center-reviewed-baseline-v0.1.json"
BASELINE_MANIFEST_SHA256 = "08372823c308cbc28f7ae91a12a6cee1d158b05c7c6444ed2b1a13bb00f48b03"
VERSION = "0.2-candidate"
COLLECTOR_VERSION = "0.1"
BASELINE_VERSION = "0.2"
SYNCED_BLOCKED = "CONTROL_CENTER_EVIDENCE_SYNCED_BLOCKED"
REVIEW_CANDIDATE = "CONTROL_CENTER_REDUCED_SURFACE_REVIEW_CANDIDATE"
FAIL_CLOSED = "CONTROL_CENTER_EVIDENCE_SYNC_FAIL_CLOSED"
REDUCED_SURFACE_ONLY = "REDUCED_SURFACE_ONLY"
RESPONSE_DATE = "2026-09-16"
REVIEWED_BASE_COMMIT = "365d616b3581b2c6db6f4e2165ec07a4e2e60275"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
VERSION_KEYS = (
    "artifact_integration", "bounded_runner", "launch_rehearsal",
    "lifecycle_filter", "lifecycle_policy", "lifecycle_receipt",
    "reduced_surface_mapping", "reduced_surface_mapping_status",
)
REQUIRED_EVIDENCE_PATHS = (
    "db/schema.sql",
    "docs/policies/revenue-mvp-official-lifecycle-policy-v20260916.md",
    "docs/policies/revenue-mvp-reduced-surface-gate-mapping-v0.1-candidate.md",
    "docs/policies/revenue-mvp-saved-lifecycle-receipt-v0.1-candidate.md",
    "scripts/build-public-data.py",
    "scripts/collect-dmm-items.py",
    "scripts/collector_preflight.py",
    "scripts/generate-saved-lifecycle-receipts.py",
    "scripts/migrate-add-lifecycle-observations.py",
    "scripts/revenue_mvp_bounded_live_verification.py",
    "scripts/revenue_mvp_bounded_verification_runner.py",
    "scripts/revenue_mvp_lifecycle_receipt.py",
    "scripts/revenue_mvp_official_lifecycle_policy.py",
    "scripts/revenue_mvp_offline_artifact_integration.py",
    "scripts/revenue_mvp_offline_launch_rehearsal.py",
    "scripts/revenue_mvp_offline_lifecycle_filter.py",
    "scripts/revenue_mvp_reduced_surface_gate_mapping.py",
    "scripts/sanitized_affiliate_observation.py",
    "tests/test_lifecycle_observation_persistence.py",
    "tests/test_revenue_mvp_builder_lifecycle_prefilter.py",
    "tests/test_revenue_mvp_saved_lifecycle_receipts.py",
)
BUILDER_PREFILTER_PATHS = (
    "scripts/build-public-data.py",
    "tests/test_revenue_mvp_builder_lifecycle_prefilter.py",
)
SAVED_RECEIPT_PATHS = (
    "scripts/generate-saved-lifecycle-receipts.py",
    "tests/test_revenue_mvp_saved_lifecycle_receipts.py",
)


@dataclass(frozen=True)
class ReviewedBaseline:
    manifest_version: str
    review_status: str
    reviewed_base_ref: str
    reviewed_base_commit: str
    official_response_received_on: str
    official_response_scope: str
    expected_versions: tuple[tuple[str, str], ...]
    required_evidence_sha256: tuple[tuple[str, str], ...]
    builder_prefilter_evidence_paths: tuple[str, ...]
    saved_receipt_evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class CollectedControlCenterEvidence:
    collector_version: str
    current_versions: tuple[tuple[str, str], ...]
    current_evidence_sha256: tuple[tuple[str, str], ...]
    missing_paths: tuple[str, ...]
    read_error: bool
    source_db_artifact_binding_verified: bool
    production_d1_read_only_reconfirmed: bool
    manual_reduced_surface_gate_approved: bool
    full_surface_official_confirmation_received: bool


@dataclass(frozen=True)
class ControlCenterEvidenceSync:
    version: str
    status: str
    official_response_pending: bool
    official_response_scope: str
    reduced_surface_review_candidate: bool
    full_surface_official_confirmation_pending: bool
    lifecycle_pipeline_verified: bool
    source_db_artifact_binding_verified: bool
    production_d1_read_only_reconfirmed: bool
    manual_reduced_surface_gate_approved: bool
    publication_allowed: bool
    production_activation_allowed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    next_action: str
    blocker_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["blocker_codes"] = list(self.blocker_codes)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _canonical_bytes(value: bytes) -> bytes:
    text = value.decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _baseline_digest(value: ReviewedBaseline) -> str:
    payload = {
        "manifest_version": value.manifest_version,
        "review_status": value.review_status,
        "reviewed_base_ref": value.reviewed_base_ref,
        "reviewed_base_commit": value.reviewed_base_commit,
        "official_response_received_on": value.official_response_received_on,
        "official_response_scope": value.official_response_scope,
        "expected_versions": dict(value.expected_versions),
        "required_evidence_sha256": dict(value.required_evidence_sha256),
        "builder_prefilter_evidence_paths": list(value.builder_prefilter_evidence_paths),
        "saved_receipt_evidence_paths": list(value.saved_receipt_evidence_paths),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _pairs(value: Any) -> tuple[tuple[str, str], ...] | None:
    if not isinstance(value, dict):
        return None
    if any(type(key) is not str or type(item) is not str for key, item in value.items()):
        return None
    return tuple(sorted(value.items()))


def parse_reviewed_baseline(value: Any) -> ReviewedBaseline | None:
    """Parse structure only; the evaluator verifies the independent digest."""
    try:
        exact_keys = {
            "manifest_version", "review_status", "reviewed_base_ref",
            "reviewed_base_commit", "official_response_received_on",
            "official_response_scope", "expected_versions",
            "required_evidence_sha256", "builder_prefilter_evidence_paths",
            "saved_receipt_evidence_paths",
        }
        if type(value) is not dict or set(value) != exact_keys:
            return None
        versions = _pairs(value["expected_versions"])
        hashes = _pairs(value["required_evidence_sha256"])
        builder_paths = value["builder_prefilter_evidence_paths"]
        saved_paths = value["saved_receipt_evidence_paths"]
        if (
            versions is None or hashes is None
            or type(builder_paths) is not list or type(saved_paths) is not list
            or any(type(path) is not str for path in builder_paths + saved_paths)
        ):
            return None
        result = ReviewedBaseline(
            value["manifest_version"], value["review_status"],
            value["reviewed_base_ref"], value["reviewed_base_commit"],
            value["official_response_received_on"], value["official_response_scope"],
            versions, hashes, tuple(builder_paths), tuple(saved_paths),
        )
        return result if _baseline_is_valid(result) else None
    except Exception:
        return None


def _baseline_is_valid(value: Any) -> bool:
    if type(value) is not ReviewedBaseline:
        return False
    try:
        versions = dict(value.expected_versions)
        hashes = dict(value.required_evidence_sha256)
        return (
            value.manifest_version == BASELINE_VERSION
            and value.review_status == "REVIEWED_BASELINE"
            and value.reviewed_base_ref == "main"
            and value.reviewed_base_commit == REVIEWED_BASE_COMMIT
            and value.official_response_received_on == RESPONSE_DATE
            and value.official_response_scope == REDUCED_SURFACE_ONLY
            and len(versions) == len(value.expected_versions)
            and tuple(sorted(versions)) == VERSION_KEYS
            and len(hashes) == len(value.required_evidence_sha256)
            and tuple(sorted(hashes)) == REQUIRED_EVIDENCE_PATHS
            and value.builder_prefilter_evidence_paths == BUILDER_PREFILTER_PATHS
            and value.saved_receipt_evidence_paths == SAVED_RECEIPT_PATHS
            and all(SHA256_RE.fullmatch(digest) is not None for digest in hashes.values())
            and _baseline_digest(value) == BASELINE_MANIFEST_SHA256
        )
    except Exception:
        return False


def load_reviewed_baseline() -> ReviewedBaseline | None:
    """Load only the fixed, independently hash-bound baseline manifest."""
    try:
        content = BASELINE_PATH.read_bytes()
        return parse_reviewed_baseline(json.loads(content.decode("utf-8")))
    except Exception:
        return None


def _current_versions() -> tuple[tuple[str, str], ...]:
    mapping = gate_mapping.review_reduced_surface_gate_mapping(
        gate_mapping.current_versioned_evidence()
    )
    return tuple(sorted({
        "artifact_integration": artifact_integration.VERSION,
        "bounded_runner": bounded_runner.RUNNER_VERSION,
        "launch_rehearsal": launch_rehearsal.VERSION,
        "lifecycle_filter": lifecycle_filter.VERSION,
        "lifecycle_policy": lifecycle_policy.POLICY_VERSION,
        "lifecycle_receipt": lifecycle_receipt.LIFECYCLE_RECEIPT_VERSION,
        "reduced_surface_mapping": gate_mapping.MAPPING_VERSION,
        "reduced_surface_mapping_status": mapping.status,
    }.items()))


def collect_current_evidence(baseline: Any) -> CollectedControlCenterEvidence:
    """Collect allowlisted tracked file hashes and current contract versions."""
    hashes: list[tuple[str, str]] = []
    missing: list[str] = []
    read_error = False
    if not _baseline_is_valid(baseline):
        return CollectedControlCenterEvidence(
            COLLECTOR_VERSION, _current_versions(), (), (), True,
            False, False, False, False,
        )
    for relative, _expected in baseline.required_evidence_sha256:
        path = ROOT / relative
        try:
            if not path.is_file():
                missing.append(relative)
                continue
            hashes.append((relative, _sha256(path.read_bytes())))
        except Exception:
            read_error = True
    return CollectedControlCenterEvidence(
        COLLECTOR_VERSION, _current_versions(), tuple(sorted(hashes)),
        tuple(sorted(missing)), read_error, False, False, False, False,
    )


def _result(
    status: str, *, official_pending: bool, scope: str = "UNCONFIRMED",
    review_candidate: bool = False, lifecycle_pipeline_verified: bool = False,
    source_binding_verified: bool = False, d1_reconfirmed: bool = False,
    manual_gate_approved: bool = False, next_action: str,
    blockers: tuple[str, ...], reasons: tuple[str, ...],
) -> ControlCenterEvidenceSync:
    return ControlCenterEvidenceSync(
        VERSION, status, official_pending, scope, review_candidate, True,
        lifecycle_pipeline_verified, source_binding_verified, d1_reconfirmed,
        manual_gate_approved, False, False, False, False, next_action,
        tuple(sorted(set(blockers))), tuple(sorted(set(reasons))),
    )


def _failed(blocker: str, reason: str) -> ControlCenterEvidenceSync:
    return _result(
        FAIL_CLOSED, official_pending=True,
        next_action="RECONCILE_REVIEWED_CONTROL_CENTER_BASELINE",
        blockers=(blocker,), reasons=(reason,),
    )


def evaluate_control_center_evidence(
    baseline: Any, current: Any,
) -> ControlCenterEvidenceSync:
    """Purely compare current evidence with the independent reviewed baseline."""
    try:
        if not _baseline_is_valid(baseline):
            return _failed("REVIEWED_BASELINE_MANIFEST_INVALID", "REVIEWED_BASELINE_REQUIRED")
        if type(current) is not CollectedControlCenterEvidence:
            return _failed("CURRENT_TRACKED_EVIDENCE_INVALID", "CURRENT_TRACKED_EVIDENCE_REQUIRED")
        operational = (
            current.source_db_artifact_binding_verified,
            current.production_d1_read_only_reconfirmed,
            current.manual_reduced_surface_gate_approved,
            current.full_surface_official_confirmation_received,
            current.read_error,
        )
        if any(type(value) is not bool for value in operational):
            return _failed("CURRENT_TRACKED_EVIDENCE_MALFORMED", "CURRENT_TRACKED_EVIDENCE_BOOLEAN_INVALID")
        if current.collector_version != COLLECTOR_VERSION:
            return _failed("CURRENT_EVIDENCE_COLLECTOR_VERSION_MISMATCH", "CURRENT_EVIDENCE_COLLECTOR_NOT_REVIEWED")
        if current.missing_paths:
            return _failed("TRACKED_EVIDENCE_PATH_MISSING", "REQUIRED_TRACKED_EVIDENCE_INCOMPLETE")
        if current.read_error:
            return _failed("TRACKED_EVIDENCE_READ_FAILED", "REQUIRED_TRACKED_EVIDENCE_UNREADABLE")
        versions = dict(current.current_versions)
        hashes = dict(current.current_evidence_sha256)
        if (
            len(versions) != len(current.current_versions)
            or tuple(sorted(versions)) != VERSION_KEYS
            or len(hashes) != len(current.current_evidence_sha256)
            or tuple(sorted(hashes)) != REQUIRED_EVIDENCE_PATHS
        ):
            return _failed("CURRENT_TRACKED_EVIDENCE_MALFORMED", "CURRENT_TRACKED_EVIDENCE_SHAPE_INVALID")
        if versions != dict(baseline.expected_versions):
            return _failed("TRACKED_EVIDENCE_VERSION_MISMATCH", "UNREVIEWED_CONTRACT_VERSION_DETECTED")
        mismatched = {
            path for path, expected in baseline.required_evidence_sha256
            if hashes.get(path) != expected
        }
        if mismatched:
            blockers: list[str] = []
            if mismatched.intersection(BUILDER_PREFILTER_PATHS):
                blockers.append("BUILDER_PREFILTER_BINDING_MISMATCH")
            if mismatched.intersection(SAVED_RECEIPT_PATHS):
                blockers.append("SAVED_RECEIPT_BINDING_MISMATCH")
            other_paths = set(REQUIRED_EVIDENCE_PATHS).difference(
                BUILDER_PREFILTER_PATHS + SAVED_RECEIPT_PATHS
            )
            if mismatched.intersection(other_paths):
                blockers.append("TRACKED_EVIDENCE_HASH_MISMATCH")
            return _result(
                FAIL_CLOSED, official_pending=True,
                next_action="REVIEW_CHANGED_TRACKED_EVIDENCE",
                blockers=tuple(blockers), reasons=("REVIEWED_CONTENT_BINDING_MISMATCH",),
            )
        if current.full_surface_official_confirmation_received:
            return _result(
                FAIL_CLOSED, official_pending=False, scope=REDUCED_SURFACE_ONLY,
                next_action="PROVIDE_VERSIONED_FULL_SURFACE_EVIDENCE",
                blockers=("FULL_SURFACE_EVIDENCE_OUT_OF_SCOPE",),
                reasons=("REDUCED_SURFACE_EVIDENCE_CANNOT_CONFIRM_FULL_SURFACE",),
            )
        blockers: list[str] = []
        if not current.source_db_artifact_binding_verified:
            blockers.append("SOURCE_DB_AND_PUBLIC_ARTIFACT_REVALIDATION_REQUIRED")
        if not current.production_d1_read_only_reconfirmed:
            blockers.append("PRODUCTION_D1_READ_ONLY_RECONFIRMATION_REQUIRED")
        if not current.manual_reduced_surface_gate_approved:
            blockers.append("REDUCED_SURFACE_MANUAL_GATE_REVIEW_REQUIRED")
        if "SOURCE_DB_AND_PUBLIC_ARTIFACT_REVALIDATION_REQUIRED" in blockers:
            next_action = "REVALIDATE_SOURCE_DB_AND_PUBLIC_ARTIFACT"
        elif "PRODUCTION_D1_READ_ONLY_RECONFIRMATION_REQUIRED" in blockers:
            next_action = "RECONFIRM_PRODUCTION_D1_READ_ONLY"
        elif "REDUCED_SURFACE_MANUAL_GATE_REVIEW_REQUIRED" in blockers:
            next_action = "REVIEW_REDUCED_SURFACE_GATE_MANUALLY"
        else:
            next_action = "REVIEW_SEPARATE_PUBLICATION_GATE"
        return _result(
            SYNCED_BLOCKED if blockers else REVIEW_CANDIDATE,
            official_pending=False, scope=REDUCED_SURFACE_ONLY,
            review_candidate=True, lifecycle_pipeline_verified=True,
            source_binding_verified=current.source_db_artifact_binding_verified,
            d1_reconfirmed=current.production_d1_read_only_reconfirmed,
            manual_gate_approved=current.manual_reduced_surface_gate_approved,
            next_action=next_action, blockers=tuple(blockers),
            reasons=(
                "FULL_SURFACE_OFFICIAL_CONFIRMATION_STILL_PENDING",
                "OFFICIAL_RESPONSE_REFLECTED_FOR_REDUCED_SURFACE_ONLY",
                "PUBLICATION_AND_PRODUCTION_REMAIN_CLOSED",
                "REVIEWED_TRACKED_EVIDENCE_MATCHED",
            ),
        )
    except Exception:
        return _failed("CONTROL_CENTER_EVIDENCE_INTERNAL_ERROR", "CONTROL_CENTER_EVIDENCE_SYNC_FAILED")


def current_sync() -> ControlCenterEvidenceSync:
    baseline = load_reviewed_baseline()
    if baseline is None:
        return _failed("REVIEWED_BASELINE_MANIFEST_INVALID", "REVIEWED_BASELINE_REQUIRED")
    return evaluate_control_center_evidence(baseline, collect_current_evidence(baseline))


def main() -> int:
    result = current_sync()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == REVIEW_CANDIDATE else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASELINE_MANIFEST_SHA256", "BASELINE_PATH", "BUILDER_PREFILTER_PATHS",
    "COLLECTOR_VERSION", "CollectedControlCenterEvidence",
    "ControlCenterEvidenceSync", "FAIL_CLOSED", "REDUCED_SURFACE_ONLY",
    "REQUIRED_EVIDENCE_PATHS", "REVIEW_CANDIDATE", "ReviewedBaseline",
    "SAVED_RECEIPT_PATHS", "SYNCED_BLOCKED", "VERSION",
    "collect_current_evidence", "current_sync", "evaluate_control_center_evidence",
    "load_reviewed_baseline", "parse_reviewed_baseline",
]
