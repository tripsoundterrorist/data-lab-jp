"""Pure composition of development readiness and usage protection."""

from __future__ import annotations

from dataclasses import dataclass

import development_gate_evidence as gate_core
import development_usage_protection_permit as usage_core


CONTRACT_VERSION = "0.1"


@dataclass(frozen=True)
class NextGateUsageDecision:
    contract_version: str
    status: str
    next_gate_allowed: bool
    checkpoint_required: bool
    reason_codes: tuple[str, ...]


def _decision(status: str, allowed: bool, checkpoint: bool,
              *reasons: str) -> NextGateUsageDecision:
    return NextGateUsageDecision(
        CONTRACT_VERSION, status, allowed, checkpoint, tuple(reasons)
    )


def evaluate(development_evidence: object,
             usage_evidence: object) -> NextGateUsageDecision:
    """Allow selection only when both independent contracts permit it."""
    gate = gate_core.evaluate(development_evidence)
    if gate.status == "EVIDENCE_REJECTED":
        return _decision(
            "DEVELOPMENT_EVIDENCE_REJECTED", False, False,
            "DEVELOPMENT_GATE_EVIDENCE_REJECTED", *gate.reason_codes,
        )
    if gate.status != "NEXT_GATE_READY":
        return _decision(
            "NEXT_GATE_NOT_READY", False, False,
            "DEVELOPMENT_GATE_NOT_READY", *gate.reason_codes,
        )

    usage = usage_core.evaluate(usage_evidence)
    if not usage.new_task_allowed:
        return _decision(
            "USAGE_PROTECTION_BLOCKED", False, usage.checkpoint_required,
            "USAGE_PROTECTION_NOT_PERMITTED", *usage.reason_codes,
        )

    return _decision(
        "NEXT_GATE_PERMITTED", True, False,
        "DEVELOPMENT_AND_USAGE_EVIDENCE_COMPLETE",
    )


__all__ = ["CONTRACT_VERSION", "NextGateUsageDecision", "evaluate"]
