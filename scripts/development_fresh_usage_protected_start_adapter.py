"""Default-disabled freshness guard for usage-protected Gate start."""

from __future__ import annotations

from typing import Callable

import development_gate_coordinator as coordinator
import development_usage_evidence_freshness as freshness_core
import development_usage_protected_start_adapter as protected_start


ADAPTER_VERSION = "0.1"
_TEST_TOKEN = object()

StartAdapter = Callable[[object], coordinator.DevelopmentGateActionResult]


def _failed(*reasons: str) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION,
        "START_NEXT_GATE",
        coordinator.ACTION_FAILED,
        None,
        tuple(reasons),
    )


class FreshUsageProtectedStartAdapter:
    """Compose freshness and usage guards around an injected start adapter."""

    def __init__(self, downstream: StartAdapter | None = None,
                 snapshot: object = None,
                 evaluated_at_epoch_s: object = None,
                 token: object | None = None):
        self._enabled = token is _TEST_TOKEN
        self._downstream = downstream if self._enabled else None
        self._snapshot = snapshot if self._enabled else None
        self._evaluated_at_epoch_s = (
            evaluated_at_epoch_s if self._enabled else None
        )

    @classmethod
    def disabled(cls) -> "FreshUsageProtectedStartAdapter":
        return cls()

    @classmethod
    def _for_test(cls, downstream: StartAdapter, snapshot: object,
                  *, evaluated_at_epoch_s: object
                  ) -> "FreshUsageProtectedStartAdapter":
        return cls(
            downstream, snapshot, evaluated_at_epoch_s, _TEST_TOKEN
        )

    def __call__(self, development_evidence: object
                 ) -> coordinator.DevelopmentGateActionResult:
        if not self._enabled:
            return _failed("FRESH_USAGE_START_ADAPTER_DISABLED")

        freshness = freshness_core.evaluate(
            self._snapshot,
            evaluated_at_epoch_s=self._evaluated_at_epoch_s,
        )
        if freshness.status != "SNAPSHOT_FRESH" or freshness.evidence is None:
            reasons = ["FRESH_USAGE_START_BLOCKED"]
            if freshness.checkpoint_required:
                reasons.append("USAGE_CHECKPOINT_REQUIRED")
            reasons.extend(freshness.reason_codes)
            return _failed(*reasons)

        guarded = protected_start.UsageProtectedStartAdapter._for_test(
            self._downstream, freshness.evidence
        )
        return guarded(development_evidence)


__all__ = ["ADAPTER_VERSION", "FreshUsageProtectedStartAdapter"]
