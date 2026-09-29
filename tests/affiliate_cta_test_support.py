from dataclasses import replace

import revenue_mvp_current_state


def closed_revenue_state():
    """Historical closed state used by the inert pre-activation unit contracts."""
    return replace(
        revenue_mvp_current_state.current_state(),
        status=revenue_mvp_current_state.LIVE_AFFILIATE_CLOSED,
        edge_artifact_verified=True,
        affiliate_runtime_candidate_ready=True,
        affiliate_d1_lookup_ready=True,
        affiliate_d1_enabled_row_count=0,
        cta_allowed=False,
        affiliate_integration_allowed=False,
        production_write_allowed=False,
        paid_plan_change_allowed=False,
    )
