"""Unattested runtime preflight evidence candidate contract v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import queue_storage_inspection_callable_binding as callable_binding
import queue_storage_inspection_payload_schema as schema


EVIDENCE_VERSION = "0.1"
PROVENANCE = "BUILTIN_RUNTIME_PREFLIGHT_CANDIDATE"


@dataclass(frozen=True)
class RuntimePreflightEvidence:
    evidence_version: str
    binding_version: str
    callable_module: str
    callable_name: str
    provenance: str
    observed_codes: tuple[str, ...]
    production_write_disabled: bool
    queue_identity_valid: bool
    max_runtime_seconds: int


@dataclass(frozen=True)
class EvidenceValidation:
    evidence_version: str
    status: str
    evidence_schema_valid: bool
    binding_valid: bool
    identity_valid: bool
    evidence_attested: bool
    activation_allowed: bool
    invocation_allowed: bool
    reason_codes: tuple[str, ...]


def _result(status: str, reasons: tuple[str, ...], *, schema_valid: bool = False,
            binding_valid: bool = False, identity_valid: bool = False
            ) -> EvidenceValidation:
    return EvidenceValidation(
        EVIDENCE_VERSION, status, schema_valid, binding_valid, identity_valid,
        False, False, False, tuple(sorted(set(reasons))))


def _exact_candidate(value: Any) -> bool:
    expected_binding = callable_binding.get_binding()
    return (
        type(value) is RuntimePreflightEvidence
        and value.evidence_version == EVIDENCE_VERSION
        and value.binding_version == expected_binding.binding_version
        and value.callable_module == expected_binding.callable_module
        and value.callable_name == expected_binding.callable_name
        and value.provenance == PROVENANCE
        and value.observed_codes == schema.PREFLIGHT_CODES
        and value.production_write_disabled is True
        and value.queue_identity_valid is True
        and value.max_runtime_seconds == schema.MAX_RUNTIME_SECONDS
    )


def validate_candidate(evidence: Any, binding: Any,
                       queue_identity: Any) -> EvidenceValidation:
    """Validate claim shape without treating caller data as attested evidence."""
    try:
        bound = callable_binding.validate_binding(binding, queue_identity)
        if not bound.binding_valid or not bound.identity_preflight_valid:
            return _result(
                "RUNTIME_PREFLIGHT_EVIDENCE_REJECTED",
                ("BINDING_PREFLIGHT_INVALID",),
                binding_valid=bound.binding_valid,
                identity_valid=bound.identity_preflight_valid)
        if not _exact_candidate(evidence):
            return _result(
                "RUNTIME_PREFLIGHT_EVIDENCE_REJECTED",
                ("EVIDENCE_CONTRACT_INVALID",),
                binding_valid=True, identity_valid=True)
        return _result(
            "RUNTIME_PREFLIGHT_EVIDENCE_UNATTESTED",
            ("TRUSTED_EVIDENCE_COLLECTOR_REQUIRED",), schema_valid=True,
            binding_valid=True, identity_valid=True)
    except Exception:
        return _result(
            "RUNTIME_PREFLIGHT_EVIDENCE_REJECTED",
            ("EVIDENCE_VALIDATION_INTERNAL_ERROR",))
