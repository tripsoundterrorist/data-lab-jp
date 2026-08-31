"""Default-disabled usage guard for a next-Gate start adapter."""

from __future__ import annotations

from typing import Callable

import development_gate_coordinator as coordinator
import development_next_gate_usage_permit as permit_core


ADAPTER_VERSION = "0.1"
_TEST_TOKEN = object()

StartAdapter = Callable[[object], coordinator.DevelopmentGateActionResult]


def _result(status: str, *reasons: str) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION,
        "START_NEXT_GATE",
        status,
        None,
        tuple(reasons),
    )


class UsageProtectedStartAdapter:
    """Guard an injected adapter; provide no built-in start implementation."""

    def __init__(self, downstream: StartAdapter | None = None,
                 usage_evidence: object = None, token: object | None = None):
        self._enabled = token is _TEST_TOKEN
        self._downstream = downstream if self._enabled else None
        self._usage_evidence = usage_evidence if self._enabled else None

    @classmethod
    def disabled(cls) -> "UsageProtectedStartAdapter":
        return cls()

    @classmethod
    def _for_test(cls, downstream: StartAdapter,
                  usage_evidence: object) -> "UsageProtectedStartAdapter":
        return cls(downstream, usage_evidence, _TEST_TOKEN)

    def __call__(self, development_evidence: object
                 ) -> coordinator.DevelopmentGateActionResult:
        if not self._enabled:
            return _result(
                coordinator.ACTION_FAILED,
                "USAGE_PROTECTED_START_ADAPTER_DISABLED",
            )

        decision = permit_core.evaluate(
            development_evidence, self._usage_evidence
        )
        if not decision.next_gate_allowed:
            reasons = ["USAGE_PROTECTED_START_BLOCKED"]
            if decision.checkpoint_required:
                reasons.append("USAGE_CHECKPOINT_REQUIRED")
            reasons.extend(decision.reason_codes)
            return _result(coordinator.ACTION_FAILED, *reasons)

        if not callable(self._downstream):
            return _result(
                coordinator.ACTION_FAILED, "DOWNSTREAM_START_ADAPTER_INVALID"
            )
        try:
            result = self._downstream(development_evidence)
        except Exception:
            return _result(
                coordinator.ACTION_FAILED, "DOWNSTREAM_START_EXCEPTION"
            )

        if not isinstance(result, coordinator.DevelopmentGateActionResult):
            return _result(
                coordinator.ACTION_FAILED, "DOWNSTREAM_START_RESULT_INVALID"
            )
        if (result.result_version != coordinator.ACTION_RESULT_VERSION or
                result.action != "START_NEXT_GATE" or
                result.status not in {
                    coordinator.ACTION_SUCCEEDED,
                    coordinator.ACTION_FAILED,
                    coordinator.ACTION_UNCERTAIN,
                } or result.evidence is not None or
                type(result.reason_codes) is not tuple):
            return _result(
                coordinator.ACTION_FAILED, "DOWNSTREAM_START_RESULT_INVALID"
            )
        return result


__all__ = ["ADAPTER_VERSION", "UsageProtectedStartAdapter"]
