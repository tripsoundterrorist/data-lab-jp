"""Trusted read-only preflight evidence collector v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import queue_storage_inspection_callable_binding as callable_binding
import queue_storage_inspection_preflight_evidence as evidence_contract
import unattended_queue_persistence as persistence


COLLECTOR_VERSION = "0.1"


@dataclass(frozen=True)
class EvidenceCollectionResult:
    collector_version: str
    status: str
    evidence: evidence_contract.RuntimePreflightEvidence | None
    evidence_attested: bool
    activation_allowed: bool
    invocation_allowed: bool
    reason_codes: tuple[str, ...]


def _result(status: str, reasons: tuple[str, ...], *,
            evidence: evidence_contract.RuntimePreflightEvidence | None = None,
            attested: bool = False) -> EvidenceCollectionResult:
    return EvidenceCollectionResult(
        COLLECTOR_VERSION, status, evidence, attested, False, False,
        tuple(sorted(set(reasons))))


def _candidate(binding: callable_binding.CallableBinding
               ) -> evidence_contract.RuntimePreflightEvidence:
    return evidence_contract.RuntimePreflightEvidence(
        evidence_contract.EVIDENCE_VERSION, binding.binding_version,
        binding.callable_module, binding.callable_name,
        evidence_contract.PROVENANCE, binding.preflight_codes, True, True,
        binding.max_runtime_seconds)


def collect(binding: Any, queue_identity: Any) -> EvidenceCollectionResult:
    """Attest fixed read-only store construction without invoking inspection."""
    try:
        validated_binding = callable_binding.validate_binding(
            binding, queue_identity)
        if (not validated_binding.binding_valid
                or not validated_binding.identity_preflight_valid):
            return _result(
                "PREFLIGHT_EVIDENCE_COLLECTION_BLOCKED",
                ("BINDING_PREFLIGHT_INVALID",))
        queue_store, checkpoint_store = persistence._production_stores()
        fixed_queue_path = persistence.resolve_production_queue_path()
        fixed_checkpoint_root = persistence.resolve_production_checkpoint_root(
            queue_identity)
        read_only = (
            queue_store._write_enabled is False
            and checkpoint_store._write_enabled is False
            and queue_store._checkpoint_storage is checkpoint_store
            and queue_store.queue_path == fixed_queue_path
            and fixed_checkpoint_root is not None
            and checkpoint_store.objects_dir == fixed_checkpoint_root
        )
        if not read_only:
            return _result(
                "PREFLIGHT_EVIDENCE_COLLECTION_BLOCKED",
                ("PRODUCTION_WRITE_DISABLE_NOT_PROVEN",))
        candidate = _candidate(binding)
        validated_evidence = evidence_contract.validate_candidate(
            candidate, binding, queue_identity)
        if not validated_evidence.evidence_schema_valid:
            return _result(
                "PREFLIGHT_EVIDENCE_COLLECTION_BLOCKED",
                ("EVIDENCE_SCHEMA_INVALID",))
        return _result(
            "PREFLIGHT_EVIDENCE_COLLECTED",
            ("READ_ONLY_PREFLIGHT_ATTESTED_ACTIVATION_BLOCKED",),
            evidence=candidate, attested=True)
    except Exception:
        return _result(
            "PREFLIGHT_EVIDENCE_COLLECTION_BLOCKED",
            ("EVIDENCE_COLLECTION_INTERNAL_ERROR",))
