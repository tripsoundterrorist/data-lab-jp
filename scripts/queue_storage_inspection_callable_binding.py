"""Pure non-invoking callable binding for Queue storage inspection v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import queue_storage_inspection_executor_decision as executor_decision
import queue_storage_inspection_payload_schema as schema
import unattended_job_queue as core
import unattended_queue_persistence as persistence


BINDING_VERSION = "0.1"
CALLABLE_MODULE = "unattended_queue_persistence"
CALLABLE_NAME = "inspect_production_queue_storage"
RETURN_TYPE = "ProductionStorageInspectionResult"
PROVENANCE = "BUILTIN_POLICY"
_BOUND_CALLABLE = persistence.inspect_production_queue_storage


@dataclass(frozen=True)
class CallableBinding:
    binding_version: str
    job_type: str
    callable_module: str
    callable_name: str
    return_type: str
    provenance: str
    argument_codes: tuple[str, ...]
    preflight_codes: tuple[str, ...]
    max_runtime_seconds: int
    output_codes: tuple[str, ...]
    required_decision_version: str
    required_decision_status: str


@dataclass(frozen=True)
class BindingValidation:
    binding_version: str
    status: str
    binding_valid: bool
    identity_preflight_valid: bool
    production_write_preflight_valid: bool
    runtime_preflight_required: bool
    invocation_allowed: bool
    production_write_allowed: bool
    max_runtime_seconds: int | None
    reason_codes: tuple[str, ...]


def get_binding() -> CallableBinding:
    return CallableBinding(
        BINDING_VERSION, schema.JOB_TYPE, CALLABLE_MODULE, CALLABLE_NAME,
        RETURN_TYPE, PROVENANCE, (), schema.PREFLIGHT_CODES,
        schema.MAX_RUNTIME_SECONDS, schema.OUTPUT_CODES,
        executor_decision.EXECUTOR_DECISION_VERSION,
        "EXECUTOR_ACTIVATION_BLOCKED")


def _result(status: str, reasons: tuple[str, ...], *, binding_valid: bool = False,
            identity_valid: bool = False) -> BindingValidation:
    return BindingValidation(
        BINDING_VERSION, status, binding_valid, identity_valid, False, True,
        False, False, schema.MAX_RUNTIME_SECONDS if binding_valid else None,
        tuple(sorted(set(reasons))))


def validate_binding(binding: Any, queue_identity: Any) -> BindingValidation:
    """Pin the callable symbol and identity without executing runtime preflights."""
    try:
        if type(binding) is not CallableBinding or binding != get_binding():
            return _result(
                "CALLABLE_BINDING_REJECTED", ("BINDING_CONTRACT_INVALID",))
        target = getattr(persistence, CALLABLE_NAME, None)
        if target is not _BOUND_CALLABLE:
            return _result(
                "CALLABLE_BINDING_REJECTED", ("CALLABLE_TARGET_UNAVAILABLE",))
        if (type(queue_identity) is not core.QueueIdentity
                or not core.validate_queue_identity(queue_identity)):
            return _result(
                "CALLABLE_BINDING_REJECTED", ("QUEUE_IDENTITY_INVALID",),
                binding_valid=True)
        return _result(
            "CALLABLE_BOUND_PREFLIGHT_PENDING",
            ("PRODUCTION_WRITE_PREFLIGHT_PENDING",
             "RUNTIME_ACTIVATION_GATE_REQUIRED"),
            binding_valid=True, identity_valid=True)
    except Exception:
        return _result(
            "CALLABLE_BINDING_REJECTED", ("BINDING_VALIDATION_INTERNAL_ERROR",))
