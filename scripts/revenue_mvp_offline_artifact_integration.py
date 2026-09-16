"""Filter actual in-memory Public Data artifacts through merged P0 contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

import publication_artifact_validator as validator
import revenue_mvp_offline_lifecycle_filter as lifecycle_filter
import revenue_mvp_reduced_surface_semantics as reduced_surface


VERSION = "0.1-candidate"
COMPLETE = "OFFLINE_ARTIFACT_FILTER_COMPLETE"
FAIL_CLOSED = "OFFLINE_ARTIFACT_FILTER_FAIL_CLOSED"


@dataclass(frozen=True)
class OfflineArtifactItemEvidence:
    lifecycle: lifecycle_filter.OfflineLifecycleFilterResult
    reduced_surface: reduced_surface.ReducedSurfaceReview


@dataclass(frozen=True)
class OfflineArtifactIntegrationResult:
    version: str
    status: str
    files: dict[str, bytes]
    input_item_count: int
    included_item_count: int
    excluded_item_count: int
    production_publication_allowed: bool
    publication_gate_change_allowed: bool
    external_io_performed: bool
    reason_codes: tuple[str, ...]


def _failed(code: str) -> OfflineArtifactIntegrationResult:
    return OfflineArtifactIntegrationResult(
        VERSION, FAIL_CLOSED, {}, 0, 0, 0, False, False, False, (code,),
    )


def _json_bytes(value: Any) -> bytes:
    text = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return (text + "\n").encode("utf-8")


def _detail_path(public_id: str) -> str:
    return f"items/{public_id[4:6]}/{public_id}.json"


def _detail_digest(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(key for key in files if key.startswith("items/")):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path])
    return digest.hexdigest()


def _include(value: OfflineArtifactItemEvidence) -> bool:
    lifecycle = value.lifecycle
    surface = value.reduced_surface
    return (
        type(lifecycle) is lifecycle_filter.OfflineLifecycleFilterResult
        and type(surface) is reduced_surface.ReducedSurfaceReview
        and lifecycle.status == lifecycle_filter.INCLUDE_CANDIDATE
        and lifecycle.include_in_offline_artifact is True
        and lifecycle.production_cta_allowed is False
        and lifecycle.publication_allowed is False
        and lifecycle.index_detail_filter_required is True
        and lifecycle.public_rank_allowed is False
        and lifecycle.source_position_allowed is False
        and lifecycle.update_frequency_claim_allowed is False
        and surface.status == reduced_surface.REVIEW_CANDIDATE
        and surface.surface_contract_satisfied is True
        and surface.publication_gate_change_allowed is False
        and surface.production_publication_allowed is False
        and surface.api_observed_at == lifecycle.observation_observed_at
    )


def filter_offline_publication_artifacts(
    files: Any,
    evidence_by_public_id: Any,
) -> OfflineArtifactIntegrationResult:
    """Return a new filtered artifact mapping; never writes or publishes it."""

    try:
        if not isinstance(files, Mapping) or not isinstance(
            evidence_by_public_id, Mapping
        ):
            return _failed("INPUT_CONTRACT_INVALID")
        validated = validator.validate_artifacts(files)
        if validated.artifact_validation != validator.PASS:
            return _failed("INPUT_ARTIFACT_INVALID")
        documents = {
            path: json.loads(content.decode("utf-8"))
            for path, content in files.items()
        }
        manifest = documents.get("manifest.json")
        index = documents.get("index.json")
        if (
            not isinstance(manifest, dict)
            or manifest.get("publication_status") != "local_validation_only"
            or not isinstance(index, dict)
            or not isinstance(index.get("items"), list)
        ):
            return _failed("OFFLINE_ARTIFACT_BOUNDARY_INVALID")

        identifiers = tuple(item.get("public_id") for item in index["items"])
        if (
            any(type(value) is not str for value in identifiers)
            or set(evidence_by_public_id) != set(identifiers)
            or any(
                type(value) is not OfflineArtifactItemEvidence
                for value in evidence_by_public_id.values()
            )
        ):
            return _failed("ITEM_EVIDENCE_INCOMPLETE")

        included = []
        output: dict[str, bytes] = {}
        for item in index["items"]:
            public_id = item["public_id"]
            detail_path = _detail_path(public_id)
            detail = documents.get(detail_path)
            if not isinstance(detail, dict) or not isinstance(detail.get("item"), dict):
                return _failed("INDEX_DETAIL_PAIR_INVALID")
            if not _include(evidence_by_public_id[public_id]):
                continue
            detail["item"]["affiliate_cta_eligible"] = False
            included.append(item)
            output[detail_path] = _json_bytes(detail)

        index["items"] = included
        output["index.json"] = _json_bytes(index)
        manifest["item_count"] = len(included)
        manifest["index_sha256"] = hashlib.sha256(output["index.json"]).hexdigest()
        manifest["detail_aggregate_sha256"] = _detail_digest(output)
        output["manifest.json"] = _json_bytes(manifest)

        final_validation = validator.validate_artifacts(output)
        if final_validation.artifact_validation != validator.PASS:
            return _failed("FILTERED_ARTIFACT_INVALID")
        input_count = len(identifiers)
        return OfflineArtifactIntegrationResult(
            VERSION, COMPLETE, output, input_count, len(included),
            input_count - len(included), False, False, False,
            ("INDEX_DETAIL_FILTER_APPLIED", "LOCAL_VALIDATION_ONLY"),
        )
    except Exception:
        return _failed("OFFLINE_ARTIFACT_FILTER_ERROR")


__all__ = [
    "COMPLETE", "FAIL_CLOSED", "OfflineArtifactIntegrationResult",
    "OfflineArtifactItemEvidence", "VERSION",
    "filter_offline_publication_artifacts",
]
