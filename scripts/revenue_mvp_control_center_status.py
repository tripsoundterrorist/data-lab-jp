"""Aggregate-only CONTROL CENTER status for the current Revenue MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

import revenue_mvp_current_state as live_state
import revenue_mvp_expansion_activation_progress as activation_progress
import revenue_mvp_public_expansion_readiness as expansion
import revenue_mvp_ranking_readiness as ranking


VERSION = "0.1"
ACTIVE = "REVENUE_MVP_LIVE_EXPANSION_BLOCKED"
FAIL_CLOSED = "CONTROL_CENTER_STATUS_FAIL_CLOSED"


@dataclass(frozen=True)
class ControlCenterStatus:
    version: str
    status: str
    revenue_priority: str
    limited_surface_live: bool
    live_item_count: int
    affiliate_cta_live: bool
    expansion_target_item_count: int
    expansion_lookup_ready_count: int
    expansion_redirect_ready_count: int
    expansion_runtime_ready_count: int
    next_batch_preparation_allowed: bool
    next_batch_live_execution_allowed: bool
    product_funnel_window_closed: bool
    product_funnel_review_completed: bool
    compliance_publication_confirmed: bool
    expansion_publication_allowed: bool
    ranking_implementation_review_candidate: bool
    production_write_allowed: bool
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["next_actions"] = list(self.next_actions)
        return value


def current_status() -> ControlCenterStatus:
    try:
        live = live_state.current_state()
        evidence = expansion.current_evidence()
        expansion_result = expansion.assess(evidence)
        progress = activation_progress.current_progress()
        ranking_result = ranking.assess(ranking.current_evidence())
        valid = (
            live.limited_surface_live is True
            and live.live_item_count == 100
            and live.cta_allowed is True
            and evidence.target_public_item_count == 300
            and progress.status == activation_progress.READY
            and progress.candidate_count == 300
            and progress.redirect_target_count == evidence.affiliate_redirect_ready_count
            and progress.runtime_redirect_count == evidence.runtime_revalidation_ready_count
            and expansion_result.publication_allowed is False
            and expansion_result.production_write_allowed is False
            and ranking_result.publication_allowed is False
        )
        if not valid:
            raise ValueError
        actions = ["KEEP_100_ITEM_REVENUE_SURFACE_LIVE_AND_MEASURED"]
        if not evidence.product_funnel_window_closed:
            actions.append("WAIT_FOR_PRODUCT_FUNNEL_WINDOW_END")
        if not evidence.product_funnel_review_completed:
            actions.append("COMPLETE_GA4_PRODUCT_FUNNEL_REVIEW_ON_OR_AFTER_2026_10_10")
        if not evidence.compliance_publication_confirmed:
            actions.append("OBTAIN_HASH_PINNED_OWNER_COMPLIANCE_DECISION_WHEN_READY")
        return ControlCenterStatus(
            VERSION, ACTIVE, "P0", True, live.live_item_count, True,
            evidence.target_public_item_count,
            evidence.affiliate_lookup_ready_count,
            evidence.affiliate_redirect_ready_count,
            evidence.runtime_revalidation_ready_count,
            False,
            False,
            evidence.product_funnel_window_closed,
            evidence.product_funnel_review_completed,
            evidence.compliance_publication_confirmed,
            False,
            ranking_result.implementation_review_candidate,
            False,
            tuple(actions),
        )
    except Exception:
        return ControlCenterStatus(
            VERSION, FAIL_CLOSED, "P0", False, 0, False, 0, 0, 0, 0,
            False, False, False, False, False, False, False, False,
            ("REBUILD_CURRENT_AGGREGATE_EVIDENCE",),
        )


def main() -> int:
    result = current_status()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == ACTIVE else 2


if __name__ == "__main__":
    raise SystemExit(main())
