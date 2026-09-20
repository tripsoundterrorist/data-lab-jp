"""Read-only source DB to reduced-surface artifact revalidation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Mapping

import publication_artifact_validator as validator
import publication_gate
import revenue_mvp_db_handoff_preflight as db_handoff
import revenue_mvp_official_lifecycle_policy as lifecycle_policy
import revenue_mvp_offline_artifact_integration as integration
import revenue_mvp_offline_lifecycle_filter as lifecycle_filter
import revenue_mvp_reduced_surface_semantics as reduced_surface


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1-candidate"
READY = "SOURCE_ARTIFACT_REVALIDATION_READY"
FAIL_CLOSED = "SOURCE_ARTIFACT_REVALIDATION_FAIL_CLOSED"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
SAFE_REASON_CODES = frozenset({
    "ARTIFACT_DIGEST_INVALID",
    "DATABASE_ACCESS_OR_SCHEMA_ERROR",
    "DATABASE_CHANGED_DURING_PREFLIGHT",
    "DATABASE_CHANGED_DURING_REVALIDATION",
    "DATABASE_IDENTITY_MISMATCH",
    "DATABASE_MISSING",
    "DATABASE_UNAVAILABLE",
    "EXPECTED_SHA256_REQUIRED",
    "FILTERED_ARTIFACT_INVALID",
    "FOREIGN_KEY_VIOLATIONS_PRESENT",
    "INPUT_ARTIFACT_INVALID",
    "INTEGRITY_CHECK_FAILED",
    "LIFECYCLE_CANDIDATE_REQUIRED",
    "LIFECYCLE_NOT_ELIGIBLE",
    "LIFECYCLE_RECEIPTS_INVALID",
    "LIFECYCLE_RECEIPT_MISSING",
    "LIFECYCLE_UNCONFIRMED",
    "NO_COLLECTION_RUNS",
    "NO_ITEMS",
    "NO_SNAPSHOTS",
    "OBSERVATION_NOT_ELIGIBLE",
    "OBSERVATION_RANGE_UNAVAILABLE",
    "OFFLINE_ARTIFACT_FILTER_FAILED",
    "OFFLINE_LIFECYCLE_FILTER_BLOCKED",
    "PUBLICATION_REMAINS_CLOSED",
    "READ_ONLY_ENFORCEMENT_FAILED",
    "REDUCED_SURFACE_ARTIFACT_REVALIDATED",
    "REDUCED_SURFACE_SEMANTICS_NOT_EVALUATED",
    "REDUCED_SURFACE_SEMANTICS_UNCONFIRMED",
    "REMOVED_FROM_ARTIFACT_AND_CTA",
    "REQUIRED_SCHEMA_MISSING",
    "REVALIDATION_INPUT_INVALID",
    "SOURCE_ARTIFACT_REVALIDATION_ERROR",
    "SOURCE_DATABASE_IDENTITY_VERIFIED",
    "SOURCE_SORT_UNSUPPORTED",
    "SQLITE_SIDECAR_PRESENT",
    "UNSAFE_DATABASE_ENTRY",
    "UNTRUSTED_REASON_CODE_REJECTED",
    "WRITTEN_ARTIFACT_REVALIDATION_FAILED",
    "ZERO_OR_INCONSISTENT_CANDIDATE_ITEMS",
})


@dataclass(frozen=True)
class SourceArtifactRevalidation:
    version: str
    status: str
    database_identity_verified: bool
    database_item_count: int | None
    lifecycle_receipt_count: int
    lifecycle_candidate_count: int
    reduced_surface_candidate_count: int
    input_artifact_item_count: int | None
    filtered_artifact_item_count: int | None
    artifact_validation: str
    source_db_sha256: str | None
    index_sha256: str | None
    detail_aggregate_sha256: str | None
    artifact_snapshot_sha256: str | None
    output_written: bool
    publication_allowed: bool
    production_write_performed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    api_calls: int
    network_io_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _safe_reasons(values: tuple[Any, ...]) -> tuple[str, ...]:
    accepted: set[str] = set()
    rejected = False
    for value in values:
        if type(value) is str and value in SAFE_REASON_CODES:
            accepted.add(value)
        else:
            rejected = True
    if rejected:
        accepted.add("UNTRUSTED_REASON_CODE_REJECTED")
    if not accepted:
        accepted.add("SOURCE_ARTIFACT_REVALIDATION_ERROR")
    return tuple(sorted(accepted))


def _result(
    status: str,
    *,
    reasons: tuple[str, ...],
    database_identity_verified: bool = False,
    database_item_count: int | None = None,
    lifecycle_receipt_count: int = 0,
    lifecycle_candidate_count: int = 0,
    reduced_surface_candidate_count: int = 0,
    input_artifact_item_count: int | None = None,
    filtered_artifact_item_count: int | None = None,
    artifact_validation: str = "NOT_RUN",
    source_db_sha256: str | None = None,
    index_sha256: str | None = None,
    detail_aggregate_sha256: str | None = None,
    artifact_snapshot_sha256: str | None = None,
    output_written: bool = False,
) -> SourceArtifactRevalidation:
    return SourceArtifactRevalidation(
        VERSION,
        status,
        database_identity_verified,
        database_item_count,
        lifecycle_receipt_count,
        lifecycle_candidate_count,
        reduced_surface_candidate_count,
        input_artifact_item_count,
        filtered_artifact_item_count,
        artifact_validation,
        source_db_sha256,
        index_sha256,
        detail_aggregate_sha256,
        artifact_snapshot_sha256,
        output_written,
        False,
        False,
        False,
        False,
        0,
        False,
        _safe_reasons(reasons),
    )


def _load_script(name: str, filename: str) -> Any:
    path = ROOT / "scripts" / filename
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError("script unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _default_receipts(database: Path, as_of: datetime) -> tuple[Any, ...]:
    generator = _load_script(
        "source_artifact_saved_receipts",
        "generate-saved-lifecycle-receipts.py",
    )
    return generator.generate_receipts(database, as_of=as_of)


def _default_build(
    database: Path,
    as_of: datetime,
    generated_at: datetime,
    receipts: tuple[Any, ...],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Build the safe base artifact before applying lifecycle evidence.

    The production builder prefilter is deliberately bypassed only inside this
    isolated module instance. The resulting local-validation artifact still
    uses the builder's allowlists, schema validation, secret scan, URL scan,
    disabled CTA, and deterministic digests. Lifecycle and reduced-surface
    decisions are applied immediately afterwards by the offline integration.
    """

    builder = _load_script(
        "source_artifact_public_builder",
        "build-public-data.py",
    )
    original_prefilter = builder.filter_master_items_by_lifecycle_receipts

    def retain_safe_base_items(
        master_items: dict[int, dict[str, Any]],
        _confidence_by_id: dict[int, dict[str, Any]],
        _receipts: Any,
        *,
        evaluated_at: datetime | None = None,
    ) -> tuple[dict[int, dict[str, Any]], int]:
        _ = evaluated_at
        return dict(master_items), 0

    builder.filter_master_items_by_lifecycle_receipts = retain_safe_base_items
    try:
        return builder.build_documents(
            database,
            as_of,
            generated_at,
            lifecycle_receipts=receipts,
        )
    finally:
        builder.filter_master_items_by_lifecycle_receipts = original_prefilter


def _decode_item_documents(files: Mapping[str, bytes]) -> tuple[list[Any], dict[str, Any]]:
    index = json.loads(files["index.json"].decode("utf-8"))
    items = index.get("items")
    if not isinstance(items, list):
        raise ValueError("index invalid")
    details: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("public_id"), str):
            raise ValueError("item invalid")
        public_id = item["public_id"]
        path = f"items/{public_id[4:6]}/{public_id}.json"
        details[public_id] = json.loads(files[path].decode("utf-8"))["item"]
    return items, details


def _default_item_evidence(
    files: Mapping[str, bytes],
    receipts: tuple[Any, ...],
) -> tuple[dict[str, integration.OfflineArtifactItemEvidence], tuple[str, ...]]:
    """Use only present evidence; never infer unavailable sort/disclosure facts."""

    items, details = _decode_item_documents(files)
    receipt_by_id = {
        receipt.public_id: receipt
        for receipt in receipts
        if isinstance(getattr(receipt, "public_id", None), str)
    }
    gate = publication_gate.evaluate_publication_gate(files)
    evidence: dict[str, integration.OfflineArtifactItemEvidence] = {}
    reasons: set[str] = set()
    for item in items:
        public_id = item["public_id"]
        receipt = receipt_by_id.get(public_id)
        if receipt is None:
            reasons.add("LIFECYCLE_RECEIPT_MISSING")
            continue
        decision = lifecycle_policy.evaluate_official_lifecycle_policy(
            receipt.observation,
            inventory_signal=receipt.inventory_signal,
        )
        detail = details[public_id]
        lifecycle = lifecycle_filter.filter_offline_artifact_candidate(
            decision,
            gate,
            freshness_confirmed=receipt.freshness_confirmed,
            api_order_preserved=False,
            index_field_names=tuple(item),
            detail_field_names=tuple(detail),
            cta_evidence=None,
        )
        surface = reduced_surface.review_reduced_surface(
            contract_version=reduced_surface.CONTRACT_VERSION,
            lifecycle_decision=decision,
            source_sort=None,
            public_order_matches_api=False,
            api_observed_at=decision.observation_observed_at,
            requested_sort_label=None,
            timestamp_label=reduced_surface.TIMESTAMP_LABEL,
            public_semantic_fields=(),
            public_claim_codes=(),
            affiliate_url_validated=False,
            cta_requested=False,
            disclosure_visible=False,
            disclosure_proximate=False,
        )
        if decision.state is not lifecycle_policy.EligibilityState.CANDIDATE:
            reasons.add("LIFECYCLE_UNCONFIRMED")
            reasons.update(decision.reason_codes)
        if lifecycle.status != lifecycle_filter.INCLUDE_CANDIDATE:
            reasons.add("OFFLINE_LIFECYCLE_FILTER_BLOCKED")
            reasons.update(lifecycle.reason_codes)
        if surface.status != reduced_surface.REVIEW_CANDIDATE:
            reasons.add("REDUCED_SURFACE_SEMANTICS_UNCONFIRMED")
            reasons.update(surface.reason_codes)
        evidence[public_id] = integration.OfflineArtifactItemEvidence(
            lifecycle,
            surface,
        )
    return evidence, tuple(sorted(reasons))


def _snapshot_sha256(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path])
    return digest.hexdigest()


def _safe_output_target(path: Path) -> Path:
    target = path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    target.relative_to(temp_root)
    if target == temp_root or target.exists() or target.parent.is_symlink():
        raise ValueError("unsafe output")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_output(path: Path, files: Mapping[str, bytes]) -> None:
    target = _safe_output_target(path)
    temporary = Path(tempfile.mkdtemp(prefix=f"{target.name}.tmp-", dir=target.parent))
    try:
        for relative, content in files.items():
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _read_output(path: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for entry in path.rglob("*"):
        if entry.is_symlink() or (not entry.is_dir() and not entry.is_file()):
            raise ValueError("unsafe output entry")
        if entry.is_file():
            files[entry.relative_to(path).as_posix()] = entry.read_bytes()
    return files


def _sqlite_sidecars_present(database_path: Path) -> bool:
    try:
        database = database_path.resolve()
        return any(
            Path(f"{database}{suffix}").exists()
            for suffix in SQLITE_SIDECAR_SUFFIXES
        )
    except (OSError, RuntimeError):
        return True


def _database_identity_is_stable(
    database_path: Path,
    expected_sha256: str,
) -> bool:
    if _sqlite_sidecars_present(database_path):
        return False
    try:
        result = db_handoff.preflight(database_path, expected_sha256)
    except Exception:
        return False
    return result.status == db_handoff.READY and result.identity_verified is True


def _failure_after_source_read(
    database_path: Path,
    expected_sha256: str,
    *,
    reasons: tuple[Any, ...],
    **values: Any,
) -> SourceArtifactRevalidation:
    sidecar_present = _sqlite_sidecars_present(database_path)
    identity_verified = _database_identity_is_stable(
        database_path,
        expected_sha256,
    )
    final_reasons = list(reasons)
    if sidecar_present:
        final_reasons.append("SQLITE_SIDECAR_PRESENT")
    if not identity_verified:
        final_reasons.append("DATABASE_CHANGED_DURING_REVALIDATION")
    values.pop("database_identity_verified", None)
    return _result(
        FAIL_CLOSED,
        reasons=tuple(final_reasons),
        database_identity_verified=identity_verified,
        **values,
    )


def run_revalidation(
    database_path: Path,
    expected_sha256: Any,
    *,
    as_of: datetime,
    generated_at: datetime,
    output_directory: Path | None = None,
    receipt_loader: Callable[[Path, datetime], tuple[Any, ...]] = _default_receipts,
    artifact_builder: Callable[
        [Path, datetime, datetime, tuple[Any, ...]],
        tuple[dict[str, bytes], dict[str, Any]],
    ] = _default_build,
    evidence_builder: Callable[
        [Mapping[str, bytes], tuple[Any, ...]],
        tuple[dict[str, integration.OfflineArtifactItemEvidence], tuple[str, ...]],
    ] = _default_item_evidence,
) -> SourceArtifactRevalidation:
    """Revalidate locally without API, DB writes, publication, or Gate changes."""

    source_read_started = False
    try:
        if (
            not isinstance(database_path, Path)
            or not isinstance(expected_sha256, str)
            or SHA256_RE.fullmatch(expected_sha256) is None
            or not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or not isinstance(generated_at, datetime)
            or generated_at.tzinfo is None
            or (
                output_directory is not None
                and not isinstance(output_directory, Path)
            )
        ):
            return _result(
                FAIL_CLOSED,
                reasons=("REVALIDATION_INPUT_INVALID",),
            )
        if output_directory is not None:
            _safe_output_target(output_directory)

        if _sqlite_sidecars_present(database_path):
            return _result(
                FAIL_CLOSED,
                reasons=("SQLITE_SIDECAR_PRESENT",),
                source_db_sha256=expected_sha256,
            )

        source_read_started = True
        before = db_handoff.preflight(database_path, expected_sha256)
        if before.status != db_handoff.READY or not before.identity_verified:
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=tuple(before.reason_codes),
                database_item_count=before.items_count,
                source_db_sha256=expected_sha256,
            )
        if _sqlite_sidecars_present(database_path):
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=("SQLITE_SIDECAR_PRESENT",),
                database_item_count=before.items_count,
                source_db_sha256=expected_sha256,
            )

        receipts = receipt_loader(database_path, as_of)
        if type(receipts) is not tuple:
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=("LIFECYCLE_RECEIPTS_INVALID",),
                database_item_count=before.items_count,
                source_db_sha256=expected_sha256,
            )
        files, _summary = artifact_builder(
            database_path,
            as_of,
            generated_at,
            receipts,
        )
        initial = validator.validate_artifacts(files)
        if initial.artifact_validation != validator.PASS:
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=("INPUT_ARTIFACT_INVALID",),
                database_item_count=before.items_count,
                lifecycle_receipt_count=len(receipts),
                input_artifact_item_count=initial.item_count,
                artifact_validation=initial.artifact_validation,
                source_db_sha256=expected_sha256,
            )

        item_evidence, evidence_reasons = evidence_builder(files, receipts)
        filtered = integration.filter_offline_publication_artifacts(
            files,
            item_evidence,
        )
        if filtered.status != integration.COMPLETE:
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=evidence_reasons + ("OFFLINE_ARTIFACT_FILTER_FAILED",),
                database_item_count=before.items_count,
                lifecycle_receipt_count=len(receipts),
                input_artifact_item_count=initial.item_count,
                artifact_validation="FAIL_CLOSED",
                source_db_sha256=expected_sha256,
            )
        final = validator.validate_artifacts(filtered.files)
        lifecycle_candidates = sum(
            evidence.lifecycle.status == lifecycle_filter.INCLUDE_CANDIDATE
            for evidence in item_evidence.values()
        )
        surface_candidates = sum(
            evidence.reduced_surface.status == reduced_surface.REVIEW_CANDIDATE
            for evidence in item_evidence.values()
        )
        common = {
            "database_item_count": before.items_count,
            "lifecycle_receipt_count": len(receipts),
            "lifecycle_candidate_count": lifecycle_candidates,
            "reduced_surface_candidate_count": surface_candidates,
            "input_artifact_item_count": initial.item_count,
            "filtered_artifact_item_count": final.item_count,
            "artifact_validation": final.artifact_validation,
            "source_db_sha256": expected_sha256,
        }
        if final.artifact_validation != validator.PASS:
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=evidence_reasons + ("FILTERED_ARTIFACT_INVALID",),
                **common,
            )
        if (
            type(final.item_count) is not int
            or final.item_count <= 0
            or filtered.included_item_count != final.item_count
        ):
            zero_reasons = list(evidence_reasons)
            zero_reasons.append("ZERO_OR_INCONSISTENT_CANDIDATE_ITEMS")
            if initial.item_count == 0:
                zero_reasons.extend(
                    (
                        "LIFECYCLE_CANDIDATE_REQUIRED",
                        "REDUCED_SURFACE_SEMANTICS_NOT_EVALUATED",
                    )
                )
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=tuple(zero_reasons),
                **common,
            )
        if evidence_reasons:
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=evidence_reasons,
                **common,
            )

        manifest = json.loads(filtered.files["manifest.json"].decode("utf-8"))
        index_sha256 = hashlib.sha256(filtered.files["index.json"]).hexdigest()
        detail_sha256 = manifest.get("detail_aggregate_sha256")
        if (
            manifest.get("index_sha256") != index_sha256
            or not isinstance(detail_sha256, str)
            or SHA256_RE.fullmatch(detail_sha256) is None
        ):
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=("ARTIFACT_DIGEST_INVALID",),
                **common,
            )
        snapshot_sha256 = _snapshot_sha256(filtered.files)
        written = False
        if output_directory is not None:
            _write_output(output_directory, filtered.files)
            disk_files = _read_output(output_directory.resolve())
            disk = validator.validate_artifacts(disk_files)
            if (
                disk.artifact_validation != validator.PASS
                or _snapshot_sha256(disk_files) != snapshot_sha256
            ):
                return _failure_after_source_read(
                    database_path,
                    expected_sha256,
                    reasons=("WRITTEN_ARTIFACT_REVALIDATION_FAILED",),
                    **common,
                )
            written = True
        if not _database_identity_is_stable(database_path, expected_sha256):
            changed_reasons = ["DATABASE_CHANGED_DURING_REVALIDATION"]
            if _sqlite_sidecars_present(database_path):
                changed_reasons.append("SQLITE_SIDECAR_PRESENT")
            return _result(
                FAIL_CLOSED,
                reasons=tuple(changed_reasons),
                database_identity_verified=False,
                **common,
            )
        return _result(
            READY,
            reasons=(
                "SOURCE_DATABASE_IDENTITY_VERIFIED",
                "REDUCED_SURFACE_ARTIFACT_REVALIDATED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
            index_sha256=index_sha256,
            detail_aggregate_sha256=detail_sha256,
            artifact_snapshot_sha256=snapshot_sha256,
            output_written=written,
            database_identity_verified=True,
            **common,
        )
    except Exception:
        if (
            source_read_started
            and isinstance(database_path, Path)
            and isinstance(expected_sha256, str)
            and SHA256_RE.fullmatch(expected_sha256)
        ):
            return _failure_after_source_read(
                database_path,
                expected_sha256,
                reasons=("SOURCE_ARTIFACT_REVALIDATION_ERROR",),
                source_db_sha256=expected_sha256,
            )
        return _result(
            FAIL_CLOSED,
            reasons=("SOURCE_ARTIFACT_REVALIDATION_ERROR",),
            source_db_sha256=(
                expected_sha256
                if isinstance(expected_sha256, str)
                and SHA256_RE.fullmatch(expected_sha256)
                else None
            ),
        )


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO8601") from error
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include UTC offset")
    return result.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Revalidate a source DB and reduced-surface artifact offline.",
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--as-of", type=_timestamp, required=True)
    parser.add_argument("--generated-at", type=_timestamp, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_revalidation(
        args.db,
        args.expected_sha256,
        as_of=args.as_of,
        generated_at=args.generated_at,
        output_directory=args.output,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FAIL_CLOSED",
    "READY",
    "SourceArtifactRevalidation",
    "VERSION",
    "run_revalidation",
]
